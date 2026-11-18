// Tests for third-party-licenses.mjs: `npm test` (node --test).

import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { after, describe, test } from 'node:test';

import {
	declaredLicense,
	installedPackages,
	main,
	parseMetadata,
	policyEntry,
	readZip,
	render,
	resolve,
	servedWheels,
	spdxAllowed,
	templateValues,
	vendor,
	wheelLicense,
} from './third-party-licenses.mjs';

const WEBSITE = fileURLToPath(new URL('..', import.meta.url));
const POLICY = JSON.parse(readFileSync(join(WEBSITE, 'license-policy.json'), 'utf8'));
const PERMISSIVE = ['MIT', 'ISC', 'Apache-2.0'];

const dirs = [];
after(() => dirs.forEach((dir) => rmSync(dir, { recursive: true, force: true })));
const tempDir = () => {
	const dir = mkdtempSync(join(tmpdir(), 'licenses-'));
	dirs.push(dir);
	return dir;
};

/** Writes a wheel (a zip) with Python's zipfile, so the reader is tested against the real format. */
function makeWheel(path, files) {
	execFileSync('python3', [
		'-c',
		'import json, sys, zipfile\nwith zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_DEFLATED) as z:\n    for n, t in json.loads(sys.argv[2]).items(): z.writestr(n, t)',
		path,
		JSON.stringify(files),
	]);
}

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

describe('declared licences', () => {
	test('package.json: string, legacy object and legacy array forms', () => {
		assert.equal(declaredLicense({ license: ' MIT ' }), 'MIT');
		assert.equal(declaredLicense({ license: { type: 'ISC' } }), 'ISC');
		assert.equal(declaredLicense({ licenses: [{ type: 'MIT' }, { type: 'Apache-2.0' }] }), '(MIT OR Apache-2.0)');
		assert.equal(declaredLicense({}), '');
	});

	test('wheel metadata: the PEP 639 expression, a one-line License, else the classifiers', () => {
		const meta = (text) => wheelLicense(parseMetadata(text));
		assert.equal(meta('License-Expression: MIT\nLicense: BSD\n'), 'MIT');
		assert.equal(meta('License: Apache-2.0\n'), 'Apache-2.0');
		const classifier = 'Classifier: License :: OSI Approved :: BSD License\n';
		// A whole licence text in the License field (continuation lines) is not a licence name.
		assert.equal(meta(`License: BSD 3-Clause License\n        \n        Copyright (c) 2008\n${classifier}`), 'BSD License');
		assert.equal(meta(`Name: x\n${classifier}\nLicense-Expression: GPL-3.0-only (in the body, not a header)\n`), 'BSD License');
	});
});

describe('policyEntry', () => {
	const policy = { packages: { 'a-*': { declared: 'MIT' }, 'a-b-*': { declared: 'ISC' }, c: { declared: 'MIT' }, Py_Pkg: {} } };
	test('an exact key, then the longest prefix', () => {
		assert.equal(policyEntry(policy, 'c')[0], 'c');
		assert.equal(policyEntry(policy, 'a-x')[0], 'a-*');
		assert.equal(policyEntry(policy, 'a-b-x')[0], 'a-b-*');
		assert.equal(policyEntry(policy, 'cc')[0], undefined);
	});
	test('Python names match as PyPI normalizes them', () => {
		assert.equal(policyEntry(policy, 'py.pkg', true)[0], 'Py_Pkg');
		assert.equal(policyEntry(policy, 'py.pkg')[0], undefined);
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

	test('saved texts are added, for the version they were saved for only', () => {
		const dir = tempDir();
		mkdirSync(join(dir, 'licenses'));
		writeFileSync(join(dir, 'licenses', 'NOTICE'), 'Upstream notice\r\n');
		const entry = { declared: 'MIT', version: '1.0.0', texts: [{ file: 'licenses/NOTICE', from: 'https://x/{version}/NOTICE' }], source: 'https://x/tree/{version}' };
		const resolved = resolve(pkg(), policy({ p: entry }), { dir });
		assert.deepEqual(resolved.texts, [['LICENSE', 'text'], ['NOTICE (from https://x/1.0.0/NOTICE)', 'Upstream notice']]);
		assert.equal(resolved.url, 'https://x/tree/1.0.0');
		assert.throws(() => resolve(pkg({ version: '2.0.0' }), policy({ p: entry }), { dir }), /saved for version 1\.0\.0.*vendor-licenses/);
	});
});

describe('a fixture site', () => {
	const site = () => {
		const dir = tempDir();
		const add = (name, pkg, files = {}) => {
			const path = join(dir, 'node_modules', name);
			mkdirSync(path, { recursive: true });
			writeFileSync(join(path, 'package.json'), JSON.stringify({ name, version: '1.0.0', ...pkg }));
			for (const [file, text] of Object.entries(files)) writeFileSync(join(path, file), text);
		};
		add('kept', { license: 'Apache-2.0' }, { LICENSE: 'Copyright A\r\n', NOTICE: 'Notice A', 'README.md': 'no' });
		add('served-dev', { license: 'MIT' }, { LICENSE: 'Copyright Dev' });
		writeFileSync(
			join(dir, 'package-lock.json'),
			JSON.stringify({
				lockfileVersion: 3,
				packages: {
					'': {},
					'node_modules/kept': { version: '1.0.0' },
					'node_modules/served-dev': { version: '1.0.0', dev: true },
					'node_modules/other-platform': { version: '1.0.0', optional: true },
				},
			}),
		);
		mkdirSync(join(dir, 'public', 'playground'), { recursive: true });
		makeWheel(join(dir, 'public', 'playground', 'dep-2.0-py3-none-any.whl'), {
			'dep-2.0.dist-info/METADATA': 'Metadata-Version: 2.4\nName: dep\nVersion: 2.0\nLicense-Expression: MIT\nLicense-File: LICENSE\n',
			'dep-2.0.dist-info/licenses/LICENSE': 'Copyright Dep',
			'dep/__init__.py': '',
		});
		makeWheel(join(dir, 'public', 'playground', 'bare-1.0-py3-none-any.whl'), {
			'bare-1.0.dist-info/METADATA': 'Metadata-Version: 2.1\nName: bare\nVersion: 1.0\nClassifier: License :: OSI Approved :: MIT License\n',
		});
		makeWheel(join(dir, 'public', 'playground', 'marketforge-9.9.9-py3-none-any.whl'), {
			'marketforge-9.9.9.dist-info/METADATA': 'Metadata-Version: 2.4\nName: marketforge\nVersion: 9.9.9\n',
		});
		mkdirSync(join(dir, 'licenses'));
		const policy = {
			allowed: ['Apache-2.0', 'MIT'],
			packages: {},
			python: {
				allowed: ['MIT'],
				packages: { bare: { declared: 'MIT License', license: 'MIT', version: '0.9', texts: [{ file: 'licenses/bare-LICENSE', from: 'https://x/bare/{version}/LICENSE' }] } },
			},
		};
		writeFileSync(join(dir, 'license-policy.json'), `${JSON.stringify(policy, null, '\t')}\n`);
		return dir;
	};

	test('every installed package, dev ones too, and every served wheel but MarketForge', () => {
		const dir = site();
		assert.deepEqual(installedPackages(dir).map((p) => p.name), ['kept', 'served-dev']);
		assert.deepEqual(installedPackages(dir)[0].texts, [['LICENSE', 'Copyright A'], ['NOTICE', 'Notice A']]);
		const wheels = servedWheels(dir);
		assert.deepEqual(wheels.map((w) => [w.name, w.version, w.declared, w.served]), [
			['bare', '1.0', 'MIT License', 'playground/bare-1.0-py3-none-any.whl'],
			['dep', '2.0', 'MIT', 'playground/dep-2.0-py3-none-any.whl'],
		]);
		assert.deepEqual(wheels[1].texts, [['LICENSE', 'Copyright Dep']]);
	});

	test('a stale saved text fails the build until vendor-licenses refetches it', async () => {
		const dir = site();
		process.exitCode = undefined;
		main(dir);
		assert.equal(process.exitCode, 1);
		assert.equal(existsSync(join(dir, 'public', 'third-party-licenses.txt')), false);
		process.exitCode = undefined;

		const fetched = [];
		await vendor(dir, async (url) => {
			fetched.push(url);
			return 'Copyright Bare\n';
		});
		assert.deepEqual(fetched, ['https://x/bare/1.0/LICENSE']);
		assert.equal(JSON.parse(readFileSync(join(dir, 'license-policy.json'), 'utf8')).python.packages.bare.version, '1.0');

		main(dir);
		assert.equal(process.exitCode, undefined);
		const report = readFileSync(join(dir, 'public', 'third-party-licenses.txt'), 'utf8');
		assert.match(report, /^kept {2,}1\.0\.0 {2,}Apache-2\.0$/m);
		assert.match(report, /----- NOTICE -----\n\nNotice A/);
		assert.match(report, /^bare 1\.0\nLicence: MIT\nDeclared as: MIT License\nServed as: playground\/bare-1\.0-py3-none-any\.whl/m);
		assert.match(report, /----- bare-LICENSE \(from https:\/\/x\/bare\/1\.0\/LICENSE\) -----\n\nCopyright Bare/);
		assert.doesNotMatch(report, /^marketforge 9\.9\.9$/m);
	});

	test('the zip reader reads what Python writes', () => {
		const dir = tempDir();
		const path = join(dir, 'a.whl');
		makeWheel(path, { 'a/b.txt': 'x'.repeat(5000), 'c.txt': 'hello' });
		const files = readZip(path);
		assert.equal(files.get('a/b.txt')().toString(), 'x'.repeat(5000));
		assert.equal(files.get('c.txt')().toString(), 'hello');
	});
});

describe('the repository', () => {
	test('every installed package and served wheel passes the policy', () => {
		const packages = installedPackages(WEBSITE);
		assert.ok(packages.length > 0, 'run `npm ci` first');
		const values = templateValues(WEBSITE);
		for (const p of packages) resolve(p, POLICY, { dir: WEBSITE, values });
		const wheels = servedWheels(WEBSITE);
		assert.ok(wheels.length > 0, 'run `npm run sync` first: the playground serves no wheel');
		for (const w of wheels) resolve(w, POLICY.python, { dir: WEBSITE, values, python: true });
	});

	test('what the site serves has its licence texts with a copyright notice', () => {
		const packages = installedPackages(WEBSITE);
		for (const name of ['@fontsource-variable/dm-sans', '@fontsource/dm-mono', 'pagefind', '@pagefind/default-ui', '@astrojs/starlight', 'astro']) {
			const p = packages.find((x) => x.name === name);
			assert.ok(p, `${name} is not installed`);
			const { texts } = resolve(p, POLICY, { dir: WEBSITE });
			assert.ok(texts.length > 0 && texts.every(([, t]) => /copyright/i.test(t)), `${name} has no copyright notice`);
		}
	});

	test('Pyodide carries its own, CPython\'s and Emscripten\'s licences, and says where its source is', () => {
		const pyodide = installedPackages(WEBSITE).find((p) => p.name === 'pyodide');
		assert.ok(pyodide, 'pyodide is not installed');
		const resolved = resolve(pyodide, POLICY, { dir: WEBSITE, values: { python: '3', emscripten: '5' } });
		const texts = resolved.texts.map(([, t]) => t).join('\n');
		for (const needle of ['Mozilla Public License Version 2.0', 'PYTHON SOFTWARE FOUNDATION LICENSE', 'Emscripten authors', 'musl']) {
			assert.ok(texts.includes(needle), needle);
		}
		assert.equal(resolved.url, `https://github.com/pyodide/pyodide/tree/${pyodide.version}`);
	});

	test('a served wheel without its NOTICE gets it (pyarrow)', () => {
		const entry = POLICY.python.packages.pyarrow;
		assert.ok(entry.texts.some((t) => t.file.endsWith('NOTICE.txt')));
		assert.match(readFileSync(join(WEBSITE, 'licenses', 'pyarrow', 'NOTICE.txt'), 'utf8'), /^Apache Arrow\nCopyright/);
	});
});
