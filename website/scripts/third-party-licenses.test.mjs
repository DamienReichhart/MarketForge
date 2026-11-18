// Tests for third-party-licenses.mjs: `npm test` (node --test).

import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, describe, test } from 'node:test';

import {
	declaredLicense,
	installedPackages,
	main,
	policyEntry,
	render,
	resolve,
	spdxAllowed,
} from './third-party-licenses.mjs';

const POLICY = JSON.parse(readFileSync(new URL('../license-policy.json', import.meta.url), 'utf8'));
const PERMISSIVE = ['MIT', 'ISC', 'Apache-2.0'];

describe('spdxAllowed', () => {
	for (const [expression, expected] of [
		['MIT', true],
		['mit', true],
		['GPL-3.0-only', false],
		['MIT OR GPL-3.0-only', true],
		['(GPL-3.0-only OR MIT)', true],
		['MIT AND GPL-3.0-only', false],
		['MIT AND (ISC OR GPL-2.0-only)', true],
		['(MIT AND GPL-2.0-only) OR ISC', true],
		['Apache-2.0 WITH LLVM-exception', false],
	]) {
		test(`${expression} -> ${expected}`, () => {
			assert.equal(spdxAllowed(expression, PERMISSIVE), expected);
		});
	}

	test('an allowed exception', () => {
		assert.equal(spdxAllowed('Apache-2.0 WITH LLVM-exception', PERMISSIVE, ['LLVM-exception']), true);
	});

	for (const expression of ['', 'SEE LICENSE IN LICENSE.md', 'MIT OR', '(MIT', 'MIT)', 'AND MIT', 'MIT WITH', 'MIT/X11']) {
		test(`rejects ${JSON.stringify(expression)}`, () => {
			assert.throws(() => spdxAllowed(expression, PERMISSIVE), /not an SPDX licence expression/);
		});
	}
});

describe('declaredLicense', () => {
	test('string, legacy object and legacy array forms', () => {
		assert.equal(declaredLicense({ license: ' MIT ' }), 'MIT');
		assert.equal(declaredLicense({ license: { type: 'ISC' } }), 'ISC');
		assert.equal(declaredLicense({ licenses: [{ type: 'MIT' }, { type: 'Apache-2.0' }] }), '(MIT OR Apache-2.0)');
		assert.equal(declaredLicense({}), '');
	});
});

describe('policyEntry', () => {
	const policy = { packages: { 'a-*': { declared: 'MIT' }, 'a-b-*': { declared: 'ISC' }, c: { declared: 'MIT' } } };
	test('an exact key, then the longest prefix', () => {
		assert.equal(policyEntry(policy, 'c')[0], 'c');
		assert.equal(policyEntry(policy, 'a-x')[0], 'a-*');
		assert.equal(policyEntry(policy, 'a-b-x')[0], 'a-b-*');
		assert.equal(policyEntry(policy, 'cc')[0], undefined);
	});
});

describe('resolve', () => {
	const pkg = (overrides) => ({ name: 'p', version: '1.0.0', declared: 'MIT', url: '', texts: [['LICENSE', 'text']], ...overrides });
	const policy = (packages = {}) => ({ allowed: PERMISSIVE, exceptions: [], packages });

	test('an allowed licence with its text', () => {
		assert.equal(resolve(pkg(), policy()).license, 'MIT');
	});

	test('a copyleft licence fails unless allowed for the package', () => {
		assert.throws(() => resolve(pkg({ declared: 'LGPL-3.0-or-later' }), policy()), /does not allow/);
		const allowed = policy({ p: { declared: 'LGPL-3.0-or-later', allow: ['LGPL-3.0-or-later'] } });
		assert.equal(resolve(pkg({ declared: 'LGPL-3.0-or-later' }), allowed).license, 'LGPL-3.0-or-later');
	});

	test('a licence that is not SPDX needs an entry', () => {
		assert.throws(() => resolve(pkg({ declared: 'SEE LICENSE IN x' }), policy()), /not an SPDX expression/);
		assert.throws(() => resolve(pkg({ declared: 'BSD' }), policy()), /give the right one with "license"/);
		const mapped = policy({ p: { declared: 'BSD', license: 'ISC' } });
		assert.equal(resolve(pkg({ declared: 'BSD' }), mapped).license, 'ISC');
	});

	test('an entry stops applying when the declared licence changes', () => {
		const reviewed = policy({ p: { declared: 'MIT', allow: ['GPL-3.0-only'] } });
		assert.throws(() => resolve(pkg({ declared: 'GPL-3.0-only' }), reviewed), /was reviewed for 'MIT'/);
	});

	test('a package without licence text needs one from the policy, or a reason', () => {
		assert.throws(() => resolve(pkg({ texts: [] }), policy()), /ships no licence text/);
		const notServed = resolve(pkg({ texts: [] }), policy({ p: { declared: 'MIT', notServed: 'Build only.' } }));
		assert.equal(notServed.notServed, 'Build only.');
		assert.match(render([notServed]), /No licence text is published with this package\. Build only\./);
	});
});

describe('the repository', () => {
	const dirs = [];
	after(() => dirs.forEach((dir) => rmSync(dir, { recursive: true, force: true })));

	test('every installed package passes the policy', () => {
		const packages = installedPackages(new URL('..', import.meta.url).pathname);
		assert.ok(packages.length > 0, 'run `npm ci` first');
		for (const p of packages) resolve(p, POLICY);
	});

	test('the fonts and Pagefind, which the site serves, have their licence texts', () => {
		const packages = installedPackages(new URL('..', import.meta.url).pathname);
		for (const name of ['@fontsource-variable/dm-sans', '@fontsource/dm-mono', 'pagefind', '@pagefind/default-ui', '@astrojs/starlight', 'astro']) {
			const p = packages.find((x) => x.name === name);
			assert.ok(p, `${name} is not installed`);
			const { texts } = resolve(p, POLICY);
			assert.ok(texts.length > 0 && texts.every(([, t]) => /copyright/i.test(t)), `${name} has no copyright notice`);
		}
	});

	test('a fixture tree: dev and uninstalled packages are left out, NOTICE files kept', () => {
		const dir = mkdtempSync(join(tmpdir(), 'licenses-'));
		dirs.push(dir);
		const add = (name, pkg, files = {}) => {
			const path = join(dir, 'node_modules', name);
			mkdirSync(path, { recursive: true });
			writeFileSync(join(path, 'package.json'), JSON.stringify({ name, version: '1.0.0', ...pkg }));
			for (const [file, text] of Object.entries(files)) writeFileSync(join(path, file), text);
		};
		add('kept', { license: 'Apache-2.0' }, { LICENSE: 'Copyright A\r\n', NOTICE: 'Notice A', 'README.md': 'no' });
		add('tool', { license: 'GPL-3.0-only' }, { LICENSE: 'GPL' });
		writeFileSync(
			join(dir, 'package-lock.json'),
			JSON.stringify({
				lockfileVersion: 3,
				packages: {
					'': {},
					'node_modules/kept': { version: '1.0.0' },
					'node_modules/tool': { version: '1.0.0', dev: true },
					'node_modules/other-platform': { version: '1.0.0', optional: true },
				},
			}),
		);
		const packages = installedPackages(dir);
		assert.deepEqual(packages.map((p) => p.name), ['kept']);
		assert.deepEqual(packages[0].texts, [['LICENSE', 'Copyright A'], ['NOTICE', 'Notice A']]);
		writeFileSync(join(dir, 'license-policy.json'), JSON.stringify({ allowed: ['Apache-2.0'], packages: {} }));
		mkdirSync(join(dir, 'public'));
		main(dir);
		const report = readFileSync(join(dir, 'public', 'third-party-licenses.txt'), 'utf8');
		assert.match(report, /^kept {2,}1\.0\.0 {2,}Apache-2\.0$/m);
		assert.match(report, /----- NOTICE -----\n\nNotice A/);
	});
});
