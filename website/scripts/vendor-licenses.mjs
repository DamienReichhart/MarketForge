// `npm run vendor-licenses`: fetches the licence texts license-policy.json
// saves under licenses/, for the versions installed and served now, and
// records those versions. Run it when the build says a saved text or a
// component manifest is for another version, then review the diff (a licence
// change shows there) and commit it. third-party-licenses.mjs, which runs on
// every build, only reads what this writes, offline.
//
// What it fetches, per policy entry:
//   texts               each `from` URL, to its `file`
//   textsFrom: "pypi"   the licence files of the package's PyPI release at the
//                       served version (its wheel's, else its sdist's); the list
//                       of files is rewritten, so new ones are picked up
//   components          what upstream compiled into the served files, resolved
//                       from upstream's build files and lockfiles at the served
//                       version, into a manifest with every component's texts:
//     { name, version | versionFrom, license, texts: [url], symbols? }
//                       a library, its version read from a build file
//                       (versionFrom: { url, pattern, format? })
//     { cargo: { lock, package } }
//                       the crates `package` depends on in a Cargo.lock, with
//                       their licences from crates.io
//     { npm: { lock, manifest, include? } }
//                       the packages a JavaScript bundle is built from: the
//                       manifest's dependencies and `include`, and theirs
//
// Every download a lockfile or PyPI gives a hash for is checked against it.

import { createHash } from 'node:crypto';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, posix } from 'node:path';
import { fileURLToPath } from 'node:url';

import { readTarGz, readZip } from './archives.mjs';
import {
	checked,
	cleanText,
	fillTemplate,
	LICENSE_FILE,
	loadPolicy,
	POLICY_FILE,
	parseMetadata,
	policyEntry,
	templateValues,
	websiteDir,
} from './third-party-licenses.mjs';

const USER_AGENT = 'third-party-licenses-vendor/1.0';
// The SPDX licence texts `spdx:<ID>` component texts use, at a release of the list.
const SPDX_TEXTS = 'https://raw.githubusercontent.com/spdx/license-list-data/v3.29.0/text';

// The fetch vendor() was given (tests pass one that serves fixtures).
let transport = globalThis.fetch;

async function fetchBytes(url) {
	for (let attempt = 1; ; attempt++) {
		try {
			const response = await transport(url, { headers: { 'User-Agent': USER_AGENT } });
			if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
			return Buffer.from(await response.arrayBuffer());
		} catch (error) {
			if (attempt >= 3 || /HTTP 4\d\d/.test(error.message)) throw error;
			await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
		}
	}
}
const fetchText = async (url) => (await fetchBytes(url)).toString('utf8');

function checkHash(bytes, url, { sha256, integrity }) {
	if (sha256) {
		const actual = createHash('sha256').update(bytes).digest('hex');
		if (actual !== sha256) throw new Error(`${url}: sha256 ${actual}, expected ${sha256}`);
	}
	if (integrity) {
		const [algorithm, expected] = integrity.split(' ')[0].split(/-(.*)/s);
		const actual = createHash(algorithm).update(bytes).digest('base64');
		if (actual !== expected) throw new Error(`${url}: ${algorithm} ${actual}, expected ${expected}`);
	}
}

/** Top-level licence and NOTICE files of an unpacked archive under `root/`. */
function licenceFiles(files, root) {
	return [...files.keys()]
		.filter((path) => path.startsWith(root) && !path.slice(root.length).includes('/') && LICENSE_FILE.test(posix.basename(path)))
		.sort();
}

const slug = (name) => name.toLowerCase().replace(/[^a-z0-9.+-]+/g, '-').replace(/^-|-$/g, '');
const spdx = (license) => String(license ?? '').trim().replace(/\s*\/\s*/g, ' OR ');

function save(dir, file, text) {
	const clean = cleanText(text);
	if (!clean) throw new Error(`${file}: the fetched text is empty`);
	mkdirSync(dirname(join(dir, file)), { recursive: true });
	writeFileSync(join(dir, file), `${clean}\n`);
	return file;
}

// ---------------------------------------------------------------- recipes

export async function versionOf(recipe, values, fetchText_ = fetchText) {
	// fetchText_ lets tests read a build file without the network.
	if (!recipe.versionFrom) return fillTemplate(recipe.version, values);
	const { url, pattern, format } = recipe.versionFrom;
	const source = fillTemplate(url, values);
	const match = new RegExp(pattern, 'm').exec(await fetchText_(source));
	if (!match) throw new Error(`${recipe.name}: /${pattern}/ is not in ${source} any more; fix its versionFrom`);
	if (!format) return match[1];
	return format.replace(/\{(\d+)\}/g, (_, i) => (/^\d+$/.test(match[i]) ? String(Number(match[i])) : match[i]));
}

async function library(recipe, values, out) {
	const version = await versionOf(recipe, values);
	const own = { ...values, component: version };
	const texts = [];
	for (const template of recipe.texts) {
		const from = fillTemplate(template, own);
		texts.push({ file: save(out.dir, `${out.base}/${slug(recipe.name)}/${posix.basename(new URL(from).pathname)}`, await fetchText(from)), from });
	}
	return [{ name: recipe.name, version, license: recipe.license, url: recipe.url ? fillTemplate(recipe.url, own) : undefined, texts }];
}

/** The [[package]] entries of a Cargo.lock. */
export function parseCargoLock(text) {
	return text
		.split(/^\[\[package\]\]$/m)
		.slice(1)
		.map((block) => {
			const field = (key) => new RegExp(`^${key} = "([^"]*)"`, 'm').exec(block)?.[1];
			const deps = /^dependencies = \[([^\]]*)\]/m.exec(block)?.[1] ?? '';
			return {
				name: field('name'),
				version: field('version'),
				source: field('source'),
				checksum: field('checksum'),
				dependencies: [...deps.matchAll(/"([^"]+)"/g)].map((m) => m[1].split(' ').slice(0, 2)),
			};
		});
}

async function cargo({ cargo: spec }, values, out) {
	const lockUrl = fillTemplate(spec.lock, values);
	const crates = parseCargoLock(await fetchText(lockUrl));
	const find = ([name, version]) => {
		const matches = crates.filter((c) => c.name === name && (!version || c.version === version));
		if (matches.length !== 1) throw new Error(`${lockUrl}: cannot resolve the crate ${name} ${version ?? ''}`);
		return matches[0];
	};
	const root = find([spec.package]);
	const seen = new Set([root]);
	const queue = [root];
	while (queue.length) for (const dep of queue.shift().dependencies.map(find)) if (!seen.has(dep)) seen.add(dep), queue.push(dep);
	const components = [];
	for (const crate of [...seen].filter((c) => c.source?.startsWith('registry+'))) {
		const { version } = JSON.parse(await fetchText(`https://crates.io/api/v1/crates/${crate.name}/${crate.version}`));
		const url = `https://static.crates.io/crates/${crate.name}/${crate.name}-${crate.version}.crate`;
		const bytes = await fetchBytes(url);
		checkHash(bytes, url, { sha256: crate.checksum });
		const files = readTarGz(bytes);
		const root_ = `${crate.name}-${crate.version}/`;
		const texts = licenceFiles(files, root_).map((path) => ({
			file: save(out.dir, `${out.base}/crates/${crate.name}-${crate.version}/${posix.basename(path)}`, files.get(path).toString('utf8')),
			from: `${url}#${path}`,
		}));
		components.push({ name: crate.name, version: crate.version, license: spdx(version.license), url: `https://crates.io/crates/${crate.name}/${crate.version}`, via: `Cargo.lock of ${spec.package}`, texts });
	}
	return components;
}

async function npm({ npm: spec }, values, out) {
	const lockUrl = fillTemplate(spec.lock, values);
	const lock = JSON.parse(await fetchText(lockUrl));
	const manifest = JSON.parse(await fetchText(fillTemplate(spec.manifest, values)));
	const locate = (name, from) => {
		for (let at = from; ; ) {
			const key = `${at ? `${at}/` : ''}node_modules/${name}`;
			if (lock.packages[key]) return key;
			if (!at) throw new Error(`${lockUrl}: cannot resolve ${name}`);
			at = at.includes('/node_modules/') ? at.slice(0, at.lastIndexOf('/node_modules/')) : '';
		}
	};
	const queue = [...Object.keys(manifest.dependencies ?? {}), ...(spec.include ?? [])].map((name) => locate(name, ''));
	const seen = new Set(queue);
	while (queue.length) {
		const key = queue.shift();
		const entry = lock.packages[key];
		for (const name of Object.keys({ ...entry.dependencies, ...entry.optionalDependencies })) {
			const dep = locate(name, key);
			if (!seen.has(dep)) seen.add(dep), queue.push(dep);
		}
	}
	const components = [];
	for (const key of seen) {
		const entry = lock.packages[key];
		const name = key.slice(key.lastIndexOf('node_modules/') + 'node_modules/'.length);
		const bytes = await fetchBytes(entry.resolved);
		checkHash(bytes, entry.resolved, { integrity: entry.integrity });
		const files = readTarGz(bytes);
		// npm tarballs usually unpack to package/, not always.
		const manifestPath = [...files.keys()].find((path) => /^[^/]+\/package\.json$/.test(path));
		if (!manifestPath) throw new Error(`${entry.resolved} has no package.json`);
		const pkg = JSON.parse(files.get(manifestPath).toString('utf8'));
		const texts = licenceFiles(files, manifestPath.slice(0, -'package.json'.length)).map((path) => ({
			file: save(out.dir, `${out.base}/npm/${slug(name)}-${entry.version}/${posix.basename(path)}`, files.get(path).toString('utf8')),
			from: `${entry.resolved}#${path}`,
		}));
		const author = typeof pkg.author === 'string' ? pkg.author.replace(/\s*[<(].*$/, '') : pkg.author?.name;
		components.push({ name, version: entry.version, license: spdx(entry.license ?? pkg.license), url: `https://www.npmjs.com/package/${name}/v/${entry.version}`, via: `bundled into ${manifest.name}`, author, texts });
	}
	return components;
}

/** Resolves an entry's component recipes and writes its manifest. */
async function components(entry, pkg, values, dir) {
	const base = posix.dirname(entry.components.manifest);
	const out = { dir, base: `${base}/components` };
	rmSync(join(dir, out.base), { recursive: true, force: true });
	const all = new Map();
	for (const recipe of entry.components.sources) {
		const found = recipe.cargo ? await cargo(recipe, values, out) : recipe.npm ? await npm(recipe, values, out) : await library(recipe, values, out);
		for (const { author, ...c } of found.map((c) => ({ ...c }))) {
			c.author = author;
			const key = `${c.name}@${c.version}`;
			if (all.has(key)) all.get(key).via = [all.get(key).via, c.via].filter(Boolean).join('; ') || undefined;
			else all.set(key, c);
		}
	}
	// A component whose release ships no licence file: its text from a commit, reviewed per version.
	for (const c of all.values()) {
		const urls = entry.components.componentTexts?.[`${c.name}@${c.version}`];
		if (c.texts.length || !urls) continue;
		for (const source of urls) {
			const file = `${out.base}/extra/${slug(c.name)}-${c.version}`;
			const reconstructed = /^spdx:(.+)$/.exec(source);
			if (reconstructed) {
				// No licence text exists upstream at all: the SPDX standard text of the declared licence,
				// with the copyright holder the package names itself (its package.json author).
				if (!c.author) throw new Error(`${c.name}@${c.version}: ${source} needs an author in its package.json`);
				const from = `${SPDX_TEXTS}/${reconstructed[1]}.txt`;
				const text = (await fetchText(from)).replace(/^(.*?)Copyright \(c\) <year> <copyright holders>/m, `$1Copyright (c) ${c.author}`);
				if (text.includes('<copyright holders>')) throw new Error(`${from}: no copyright line to fill`);
				c.texts.push({ file: save(dir, `${file}/${reconstructed[1]}.txt`, text), from: `${from} (reconstructed: no licence text is published; holder from its package.json)` });
			} else {
				c.texts.push({ file: save(dir, `${file}/${posix.basename(new URL(source).pathname)}`, await fetchText(source)), from: source });
			}
		}
	}
	const missing = [...all.values()].filter((c) => !c.texts.length).map((c) => `${c.name}@${c.version}`);
	if (missing.length) {
		throw new Error(
			`${pkg.name} ${pkg.version}: ${missing.join(', ')} ship(s) no licence file. Find the licence in its repository at ` +
				'the commit of that version (or the commit that added it, if it changes nothing else) and add its URL to ' +
				'"components.componentTexts" under "name@version"',
		);
	}
	const manifest = {
		$comment: `Written by \`npm run vendor-licenses\` from the "components" of ${pkg.name} in ${POLICY_FILE}; do not edit.`,
		package: pkg.name,
		version: pkg.version,
		components: [...all.values()].map(({ author, ...c }) => c).sort((a, b) => a.name.localeCompare(b.name) || a.version.localeCompare(b.version)),
	};
	writeFileSync(join(dir, entry.components.manifest), `${JSON.stringify(manifest, null, '\t')}\n`);
	console.log(`resolved ${manifest.components.length} components of ${pkg.name} ${pkg.version}`);
}

/**
 * The licence files of a Python package's PyPI release at a version: those its
 * wheel declares, and those of its sdist (top level, and LICENSES/, where
 * projects keep the licences of the code they bundle; pandas' wheels omit them).
 */
async function pypiTexts(pkg, dir) {
	const release = JSON.parse(await fetchText(`https://pypi.org/pypi/${pkg.name}/${pkg.version}/json`));
	const base = `licenses/${slug(pkg.name)}`;
	rmSync(join(dir, base), { recursive: true, force: true });
	const smallest = (kind) => release.urls.filter((u) => u.packagetype === kind).sort((a, b) => a.size - b.size)[0];
	const found = new Map(); // relative path -> { text, from }
	const wheel = smallest('bdist_wheel');
	if (wheel) {
		const bytes = await fetchBytes(wheel.url);
		checkHash(bytes, wheel.url, { sha256: wheel.digests.sha256 });
		const zip = readZip(bytes, wheel.url);
		const metadata = [...zip.keys()].find((n) => /^[^/]+\.dist-info\/METADATA$/.test(n));
		const info = metadata.slice(0, -'METADATA'.length);
		const declared = parseMetadata(zip.get(metadata)().toString('utf8')).get('license-file') ?? [];
		const members = declared.length
			? declared.map((f) => [f, [`${info}licenses/${f}`, `${info}${f}`].find((m) => zip.has(m))]).filter(([, m]) => m)
			: [...zip.keys()].filter((m) => m.startsWith(info) && LICENSE_FILE.test(posix.basename(m))).map((m) => [m.slice(info.length), m]);
		for (const [path, member] of members) found.set(path, { text: zip.get(member)().toString('utf8'), from: `${wheel.url}#${member}` });
	}
	const sdist = smallest('sdist');
	if (sdist) {
		const bytes = await fetchBytes(sdist.url);
		checkHash(bytes, sdist.url, { sha256: sdist.digests.sha256 });
		const tar = readTarGz(bytes);
		const root = `${[...tar.keys()][0].split('/')[0]}/`;
		const bundled = [...tar.keys()].filter((m) => /^LICEN[CS]ES\/[^/]+$/i.test(m.slice(root.length)));
		for (const member of [...licenceFiles(tar, root), ...bundled]) {
			const path = member.slice(root.length);
			if (!found.has(path)) found.set(path, { text: tar.get(member).toString('utf8'), from: `${sdist.url}#${member}` });
		}
	}
	if (found.size === 0) {
		throw new Error(`${pkg.name} ${pkg.version}: its PyPI release has no licence file either; save one from its repository, at a commit, with "texts"`);
	}
	return [...found].sort(([a], [b]) => a.localeCompare(b)).map(([path, { text, from }]) => ({ file: save(dir, `${base}/${path}`, text), from }));
}

// ---------------------------------------------------------------- command

export async function vendor(dir = websiteDir, { fetch = globalThis.fetch } = {}) {
	transport = fetch;
	const policy = loadPolicy(dir);
	const done = new Map();
	for (const [pkg, rules, options] of checked(dir, policy)) {
		const [key, entry] = policyEntry(rules, pkg.name, options.python);
		if (!entry || !(entry.texts?.length || entry.textsFrom || entry.components)) continue;
		if (done.has(entry)) {
			if (done.get(entry) !== pkg.version) throw new Error(`"${key}" covers ${pkg.name} at two versions (${done.get(entry)}, ${pkg.version}); split it`);
			continue;
		}
		done.set(entry, pkg.version);
		const values = { ...templateValues(dir), version: pkg.version };
		if (entry.textsFrom === 'pypi') {
			entry.texts = await pypiTexts(pkg, dir);
			console.log(`saved ${entry.texts.length} licence files of ${pkg.name} ${pkg.version} from PyPI`);
		} else {
			for (const { file, from } of entry.texts ?? []) {
				save(dir, file, await fetchText(fillTemplate(from, values)));
				console.log(`saved ${file}`);
			}
		}
		if (entry.components) await components(entry, pkg, values, dir);
		if (entry.texts?.length) entry.version = pkg.version;
	}
	writeFileSync(join(dir, POLICY_FILE), `${JSON.stringify(policy, null, '\t')}\n`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
	vendor().catch((error) => {
		console.error(`error: ${error.message}`);
		process.exitCode = 1;
	});
}

