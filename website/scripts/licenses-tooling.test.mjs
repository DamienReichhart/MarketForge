// Tests for the archive readers, the component and binary checks of
// third-party-licenses.mjs, vendor-licenses.mjs and served-packages.mjs,
// against fixtures (no network): `npm test`.

import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { after, describe, test } from 'node:test';

import { readTarGz, wasmExports } from './archives.mjs';
import { copiedFiles, packageOf } from './served-packages.mjs';
import { checkBinary, resolve } from './third-party-licenses.mjs';
import { parseCargoLock, vendor, versionOf } from './vendor-licenses.mjs';

const dirs = [];
after(() => dirs.forEach((dir) => rmSync(dir, { recursive: true, force: true })));
const tempDir = () => {
	const dir = mkdtempSync(join(tmpdir(), 'licenses-tooling-'));
	dirs.push(dir);
	return dir;
};
const write = (path, content) => {
	mkdirSync(dirname(path), { recursive: true });
	writeFileSync(path, content);
};

/** A gzipped tar of `files` (path -> text), written by Python's tarfile. */
function tarGz(files) {
	const path = join(tempDir(), 'a.tar.gz');
	execFileSync('python3', [
		'-c',
		'import io, json, sys, tarfile\nwith tarfile.open(sys.argv[1], "w:gz") as t:\n    for n, s in json.loads(sys.argv[2]).items():\n        b = s.encode(); i = tarfile.TarInfo(n); i.size = len(b); t.addfile(i, io.BytesIO(b))',
		path,
		JSON.stringify(files),
	]);
	return readFileSync(path);
}

/** A zip of `files`, written by Python's zipfile. */
function zip(files) {
	const path = join(tempDir(), 'a.whl');
	execFileSync('python3', [
		'-c',
		'import json, sys, zipfile\nwith zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_DEFLATED) as z:\n    for n, t in json.loads(sys.argv[2]).items(): z.writestr(n, t)',
		path,
		JSON.stringify(files),
	]);
	return readFileSync(path);
}

/** A WebAssembly module whose export section names `names` (enough for wasmExports). */
function wasm(names) {
	const leb = (n) => {
		const out = [];
		do {
			let byte = n & 0x7f;
			n >>>= 7;
			if (n) byte |= 0x80;
			out.push(byte);
		} while (n);
		return out;
	};
	const body = [...leb(names.length)];
	for (const name of names) body.push(...leb(name.length), ...Buffer.from(name), 0, 0);
	const custom = [0, ...leb(5), 4, ...Buffer.from('test')];
	return Buffer.from([0, 0x61, 0x73, 0x6d, 1, 0, 0, 0, ...custom, 7, ...leb(body.length), ...body]);
}

const sha = (bytes, algorithm = 'sha256', encoding = 'hex') => createHash(algorithm).update(bytes).digest(encoding);

/** A fetch that serves `routes` (url -> string or Buffer) and records what was asked. */
function fakeFetch(routes, asked = []) {
	return async (url) => {
		asked.push(url);
		const body = typeof routes === 'function' ? routes(url) : routes[url];
		return body === undefined ? new Response('not found', { status: 404 }) : new Response(body);
	};
}

describe('archives', () => {
	test('readTarGz reads what Python writes, long names included', () => {
		const long = `pkg/${'d'.repeat(120)}/LICENSE`;
		const files = readTarGz(tarGz({ 'pkg/LICENSE': 'MIT text', [long]: 'deep' }));
		assert.equal(files.get('pkg/LICENSE').toString(), 'MIT text');
		assert.equal(files.get(long).toString(), 'deep');
	});

	test('wasmExports reads the export section', () => {
		assert.deepEqual(wasmExports(wasm(['BZ2_bzCompress', 'memcpy', '_ZNSt3__24cout'])), ['BZ2_bzCompress', 'memcpy', '_ZNSt3__24cout']);
		assert.throws(() => wasmExports(Buffer.from('not wasm at all')), /not a WebAssembly module/);
	});
});

describe('checkBinary', () => {
	const setup = (exported, runtime = ['memcpy']) => {
		const dir = tempDir();
		write(join(dir, 'pkg', 'core.wasm'), wasm(exported));
		write(join(dir, 'runtime.txt'), `# C runtime\n${runtime.join('\n')}\n`);
		const pkg = { name: 'p', version: '1', dir: join(dir, 'pkg') };
		const binary = { file: 'core.wasm', ownSymbols: '^own_', runtimeSymbols: 'runtime.txt' };
		const components = [{ name: 'bzip2', symbols: '^BZ2_' }, { name: 'musl' }];
		return (names) => checkBinary(pkg, binary, components, { dir, id: 'p 1', where: 'here' });
	};

	test('every export claimed: by a component, the package or the runtime list', () => {
		setup(['BZ2_x', 'own_y', 'memcpy'])();
	});

	test('a library no component claims fails, by name', () => {
		assert.throws(setup(['BZ2_x', 'memcpy', 'brotli_decode', 'brotli_encode']), /exports 2 symbol\(s\) no component claims: brotli_decode brotli_encode/);
	});

	test('a component the binary no longer contains fails', () => {
		assert.throws(setup(['memcpy']), /no symbol of core\.wasm matches the component bzip2/);
	});
});

describe('components of a package', () => {
	const site = (manifest) => {
		const dir = tempDir();
		write(join(dir, 'licenses', 'p', 'components.json'), JSON.stringify(manifest));
		write(join(dir, 'licenses', 'p', 'c', 'LICENSE'), 'Copyright C');
		return dir;
	};
	const pkg = { name: 'p', version: '1.0', declared: 'MIT', url: '', texts: [['LICENSE', 'x']] };
	const rules = (entry) => ({ allowed: ['MIT'], packages: { p: { declared: 'MIT', components: { manifest: 'licenses/p/components.json', sources: [] }, ...entry } } });
	const component = (license) => ({ name: 'c', version: '2', license, texts: [{ file: 'licenses/p/c/LICENSE', from: 'https://x/LICENSE' }] });

	test('are listed with their texts', () => {
		const dir = site({ version: '1.0', components: [component('MIT')] });
		const { components } = resolve(pkg, rules(), { dir });
		assert.deepEqual(components[0].texts, [['LICENSE (from https://x/LICENSE)', 'Copyright C']]);
	});

	test('must have been resolved for the version installed', () => {
		const dir = site({ version: '0.9', components: [component('MIT')] });
		assert.throws(() => resolve(pkg, rules(), { dir }), /resolved for version 0\.9.*vendor-licenses/);
	});

	test('are under the policy too', () => {
		const dir = site({ version: '1.0', components: [component('GPL-3.0-only')] });
		assert.throws(() => resolve(pkg, rules(), { dir }), /component c 2 is under 'GPL-3.0-only'/);
		assert.equal(resolve(pkg, rules({ allow: ['GPL-3.0-only'] }), { dir }).components.length, 1);
	});
});

describe('vendor-licenses', () => {
	test('versionOf reads a version from a build file, reformatted', async () => {
		const recipe = { name: 'SQLite', versionFrom: { url: 'https://u/{version}/Makefile', pattern: 'sqlite-(\\d)(\\d\\d)(\\d\\d)\\d\\d', format: '{1}.{2}.{3}' } };
		const make = async (url) => (assert.equal(url, 'https://u/7/Makefile'), 'X=sqlite-3390000.tar\n');
		assert.equal(await versionOf(recipe, { version: '7' }, make), '3.39.0');
		await assert.rejects(versionOf(recipe, { version: '7' }, async () => 'gone'), /is not in https:\/\/u\/7\/Makefile any more/);
	});

	test('parseCargoLock', () => {
		const lock = '[[package]]\nname = "a"\nversion = "1.0.0"\ndependencies = [\n "b",\n "c 2.0.0",\n]\n\n[[package]]\nname = "b"\nversion = "0.1.0"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\nchecksum = "ab"\n';
		const [a, b] = parseCargoLock(lock);
		assert.deepEqual(a.dependencies, [['b'], ['c', '2.0.0']]);
		assert.equal(b.source.startsWith('registry+'), true);
		assert.equal(b.checksum, 'ab');
	});

	/** A site whose package `host` compiles in an npm bundle, a crate and a library, and serves one wheel. */
	function fixture() {
		const dir = tempDir();
		write(join(dir, 'node_modules', 'host', 'package.json'), JSON.stringify({ name: 'host', version: '3.0.0', license: 'MIT' }));
		write(join(dir, 'node_modules', 'host', 'LICENSE'), 'Copyright Host');
		write(join(dir, 'package-lock.json'), JSON.stringify({ lockfileVersion: 3, packages: { '': {}, 'node_modules/host': { version: '3.0.0' } } }));
		write(join(dir, 'public', 'whl', 'tool-1.0-py3-none-any.whl'), zip({ 'tool-1.0.dist-info/METADATA': 'Metadata-Version: 2.1\nName: tool\nVersion: 1.0\nLicense: MIT\n' }));

		const dep = tarGz({ 'package/package.json': JSON.stringify({ name: 'dep', license: 'MIT', author: 'Dep Author' }), 'package/LICENSE': 'Copyright Dep' });
		const bare = tarGz({ 'pkg/package.json': JSON.stringify({ name: 'bare', license: 'MIT', author: { name: 'Bare Author' } }) });
		const crate = tarGz({ 'c1-0.1.0/LICENSE-MIT': 'Copyright C1', 'c1-0.1.0/src/lib.rs': '' });
		const wheel = zip({ 'tool-1.0.dist-info/METADATA': 'Metadata-Version: 2.4\nName: tool\nVersion: 1.0\nLicense-File: LICENSE\n', 'tool-1.0.dist-info/licenses/LICENSE': 'Copyright Tool' });
		const sdist = tarGz({ 'tool-1.0/LICENSE': 'Copyright Tool (sdist)', 'tool-1.0/LICENSES/BUNDLED_LICENSE': 'Copyright Bundled', 'tool-1.0/NOTICE': 'Tool notice', 'tool-1.0/src/README': 'no' });
		const integrity = (bytes) => `sha512-${sha(bytes, 'sha512', 'base64')}`;
		const routes = {
			'https://u/3.0.0/package-lock.json': JSON.stringify({
				packages: {
					'': {},
					'node_modules/dep': { version: '1.0.0', resolved: 'https://u/dep.tgz', integrity: integrity(dep), license: 'MIT', dependencies: { bare: '^2' } },
					'node_modules/bare': { version: '2.0.0', resolved: 'https://u/bare.tgz', integrity: integrity(bare), license: 'MIT' },
					'node_modules/tooling': { version: '9.0.0', resolved: 'https://u/never.tgz', dev: true },
				},
			}),
			'https://u/3.0.0/package.json': JSON.stringify({ name: 'bundle', dependencies: { dep: '1' }, devDependencies: { tooling: '9' } }),
			'https://u/dep.tgz': dep,
			'https://u/bare.tgz': bare,
			'https://u/3.0.0/Cargo.lock': `[[package]]\nname = "root"\nversion = "0.0.0"\ndependencies = [\n "c1",\n]\n\n[[package]]\nname = "c1"\nversion = "0.1.0"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\nchecksum = "${sha(crate)}"\n`,
			'https://crates.io/api/v1/crates/c1/0.1.0': JSON.stringify({ version: { license: 'MIT/Apache-2.0' } }),
			'https://static.crates.io/crates/c1/c1-0.1.0.crate': crate,
			'https://u/3.0.0/Makefile': 'LIB_VERSION=1.2.3\n',
			'https://u/lib/1.2.3/COPYING': 'Copyright Lib',
			'https://pypi.org/pypi/tool/1.0/json': JSON.stringify({
				urls: [
					{ packagetype: 'bdist_wheel', url: 'https://files/tool.whl', size: wheel.length, digests: { sha256: sha(wheel) } },
					{ packagetype: 'sdist', url: 'https://files/tool.tar.gz', size: sdist.length, digests: { sha256: sha(sdist) } },
				],
			}),
			'https://files/tool.whl': wheel,
			'https://files/tool.tar.gz': sdist,
		};
		const spdxMit = 'MIT License\n\nCopyright (c) <year> <copyright holders>\n\nPermission is hereby granted';
		const policy = {
			allowed: ['MIT', 'Apache-2.0'],
			packages: {
				host: {
					declared: 'MIT',
					components: {
						manifest: 'licenses/host/components.json',
						componentTexts: { 'bare@2.0.0': ['spdx:MIT'] },
						sources: [
							{ npm: { lock: 'https://u/{version}/package-lock.json', manifest: 'https://u/{version}/package.json' } },
							{ cargo: { lock: 'https://u/{version}/Cargo.lock', package: 'root' } },
							{ name: 'Lib', versionFrom: { url: 'https://u/{version}/Makefile', pattern: '^LIB_VERSION=(\\S+)' }, license: 'MIT', texts: ['https://u/lib/{component}/COPYING'] },
						],
					},
				},
			},
			python: { allowed: ['MIT'], packages: { tool: { declared: 'MIT', textsFrom: 'pypi' } } },
		};
		write(join(dir, 'license-policy.json'), JSON.stringify(policy));
		const fetch = (asked) => fakeFetch((url) => (/\/text\/MIT\.txt$/.test(url) ? spdxMit : routes[url]), asked);
		return { dir, routes, fetch };
	}

	test('resolves every recipe into a manifest, and PyPI texts from the wheel and the sdist', async () => {
		const { dir, fetch } = fixture();
		const asked = [];
		await vendor(dir, { fetch: fetch(asked) });
		assert.ok(!asked.includes('https://u/never.tgz'), 'a dev dependency of the bundle was fetched');

		const manifest = JSON.parse(readFileSync(join(dir, 'licenses', 'host', 'components.json'), 'utf8'));
		assert.equal(manifest.version, '3.0.0');
		const byName = Object.fromEntries(manifest.components.map((c) => [c.name, c]));
		assert.deepEqual(Object.keys(byName).sort(), ['Lib', 'bare', 'c1', 'dep']);
		assert.equal(byName.c1.license, 'MIT OR Apache-2.0');
		assert.equal(byName.Lib.version, '1.2.3');
		assert.equal(readFileSync(join(dir, byName.c1.texts[0].file), 'utf8'), 'Copyright C1\n');
		const reconstructed = readFileSync(join(dir, byName.bare.texts[0].file), 'utf8');
		assert.match(reconstructed, /^MIT License\n\nCopyright \(c\) Bare Author\n/);
		assert.match(byName.bare.texts[0].from, /reconstructed: no licence text is published/);
		assert.ok(manifest.components.every((c) => !('author' in c)));

		const policy = JSON.parse(readFileSync(join(dir, 'license-policy.json'), 'utf8'));
		const tool = policy.python.packages.tool;
		assert.equal(tool.version, '1.0');
		assert.deepEqual(tool.texts.map((t) => t.file), ['licenses/tool/LICENSE', 'licenses/tool/LICENSES/BUNDLED_LICENSE', 'licenses/tool/NOTICE']);
		assert.equal(readFileSync(join(dir, 'licenses', 'tool', 'LICENSE'), 'utf8'), 'Copyright Tool\n', 'the wheel wins over the sdist');
	});

	test('refuses a download whose hash is not the lockfile\'s', async () => {
		const { dir, routes, fetch } = fixture();
		routes['https://u/dep.tgz'] = tarGz({ 'package/package.json': '{}', 'package/LICENSE': 'tampered' });
		await assert.rejects(vendor(dir, { fetch: fetch([]) }), /https:\/\/u\/dep\.tgz: sha512/);
	});

	test('a component without licence text stops the run and says what to do', async () => {
		const { dir, fetch } = fixture();
		const policy = JSON.parse(readFileSync(join(dir, 'license-policy.json'), 'utf8'));
		delete policy.packages.host.components.componentTexts;
		write(join(dir, 'license-policy.json'), JSON.stringify(policy));
		await assert.rejects(vendor(dir, { fetch: fetch([]) }), /bare@2\.0\.0 ship\(s\) no licence file.*componentTexts/);
	});
});

describe('served-packages', () => {
	test('packageOf finds the package a bundled file comes from', () => {
		const dir = tempDir();
		write(join(dir, 'node_modules', 'a', 'package.json'), JSON.stringify({ name: 'a' }));
		write(join(dir, 'node_modules', 'a', 'dist', 'package.json'), JSON.stringify({ type: 'module' }));
		write(join(dir, 'node_modules', '@s', 'b', 'package.json'), JSON.stringify({ name: '@s/b' }));
		assert.equal(packageOf(join(dir, 'node_modules', 'a', 'dist', 'x.js'), dir), 'a');
		assert.equal(packageOf('node_modules/@s/b/style.css?inline', dir), '@s/b');
		assert.equal(packageOf(join(dir, 'src', 'x.js'), dir), undefined);
		assert.equal(packageOf('\0virtual:astro:page', dir), undefined);
	});

	test('copiedFiles finds byte-for-byte copies, not small coincidences', () => {
		const dir = tempDir();
		const big = 'x'.repeat(1000);
		write(join(dir, 'pkg', 'binary.node'), big);
		write(join(dir, 'pkg', 'tiny.json'), '{}');
		write(join(dir, 'site', 'assets', 'copy.bin'), big);
		write(join(dir, 'site', 'other.json'), '{}');
		write(join(dir, 'site', 'same-size.bin'), 'y'.repeat(1000));
		assert.deepEqual(copiedFiles(join(dir, 'site'), [{ name: 'pkg', dir: join(dir, 'pkg') }]), [[join('assets', 'copy.bin'), 'pkg']]);
	});
});
