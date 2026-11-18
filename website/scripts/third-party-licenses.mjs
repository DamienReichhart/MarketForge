// Writes public/third-party-licenses.txt: the licence and NOTICE texts of
// everything third-party the website is built from or serves, so the site
// ships the notices of the code, styles, fonts and runtime it sends to
// visitors: Astro, Starlight, Expressive Code, Pagefind, the DM Sans and DM
// Mono fonts, and the playground's Pyodide (CPython, Emscripten) and Python
// wheels. Runs before every dev, check and build (`npm run sync`), after
// sync-playground.mjs, from what is installed and about to be served, so it
// cannot fall out of date:
//
//   every package of package-lock.json installed in node_modules/
//   every Python wheel under public/ except MarketForge's own
//
// Each package's licence is checked against license-policy.json (npm and
// Python packages have separate rules). The build fails when a licence is not
// allowed or is not an SPDX expression, when a package changes the licence its
// policy entry was reviewed for, when a package ships no licence text and the
// policy gives none, and when the texts the policy saved for a package
// (licenses/) were saved for another version of it.
//
//   node scripts/third-party-licenses.mjs            check and write the file
//   node scripts/third-party-licenses.mjs --vendor   refetch the saved texts for
//                                                    the installed versions
//                                                    (`npm run vendor-licenses`)

import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, posix, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { inflateRawSync } from 'node:zlib';

const websiteDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const POLICY_FILE = 'license-policy.json';
const OUTPUT = join('public', 'third-party-licenses.txt');
const LICENSE_FILE = /^(licen[cs]e|copying|notice|copyright|ofl)([-._ ].*)?$/i;
const PROJECT_WHEEL = /^marketforge-/;
const RULE = '='.repeat(79);

// ---------------------------------------------------------------- SPDX

/**
 * Whether an SPDX licence expression can be satisfied with the allowed
 * licences: `A OR B` needs one side, `A AND B` both, `A WITH E` needs A and the
 * exception E. Case-insensitive, as SPDX specifies. Throws if it does not parse.
 */
export function spdxAllowed(expression, allowed, exceptions = []) {
	const ids = new Set(allowed.map((id) => id.toLowerCase()));
	const excs = new Set(exceptions.map((id) => id.toLowerCase()));
	const tokens = String(expression).match(/\(|\)|[^\s()]+/g) ?? [];
	const bad = (why) => new Error(`'${expression}' is not an SPDX licence expression${why ? ` (${why})` : ''}`);
	const operators = new Set(['and', 'or', 'with']);
	if (tokens.length === 0 || tokens.some((t) => !/^(\(|\)|[A-Za-z0-9.+:-]+)$/.test(t))) throw bad();
	let pos = 0;
	const peek = () => tokens[pos]?.toLowerCase();
	const take = () => {
		if (pos >= tokens.length) throw bad('it ends too early');
		return tokens[pos++];
	};
	const atom = () => {
		const token = take();
		if (token === '(') {
			const value = either();
			if (take() !== ')') throw bad('unclosed parenthesis');
			return value;
		}
		if (token === ')' || operators.has(token.toLowerCase())) throw bad();
		let value = ids.has(token.toLowerCase());
		if (peek() === 'with') {
			take();
			const exception = take();
			if (exception === '(' || exception === ')' || operators.has(exception.toLowerCase())) {
				throw bad('no exception after WITH');
			}
			value = value && excs.has(exception.toLowerCase());
		}
		return value;
	};
	const both = () => {
		let value = atom();
		while (peek() === 'and') {
			take();
			value = atom() && value;
		}
		return value;
	};
	const either = () => {
		let value = both();
		while (peek() === 'or') {
			take();
			value = both() || value;
		}
		return value;
	};
	const result = either();
	if (pos !== tokens.length) throw bad();
	return result;
}

export function cleanText(text) {
	return text
		.replace(/\r\n?/g, '\n')
		.split('\n')
		.map((line) => line.trimEnd())
		.join('\n')
		.replace(/^\n+|\n+$/g, '');
}

const byName = (a, b) => (a.name === b.name ? a.version.localeCompare(b.version) : a.name < b.name ? -1 : 1);

// ---------------------------------------------------------------- npm packages

/** The licence a package.json states, as one string (legacy forms included). */
export function declaredLicense(pkg) {
	const { license, licenses } = pkg;
	if (typeof license === 'string') return license.trim();
	if (license && typeof license.type === 'string') return license.type.trim();
	if (Array.isArray(licenses)) {
		const types = licenses.map((l) => (typeof l === 'string' ? l : l?.type)).filter(Boolean);
		if (types.length) return types.length > 1 ? `(${types.join(' OR ')})` : types[0];
	}
	return '';
}

function sourceUrl(pkg) {
	const repo = typeof pkg.repository === 'string' ? pkg.repository : pkg.repository?.url;
	if (repo) {
		const url = repo.replace(/^git\+/, '').replace(/\.git$/, '').replace(/^git:\/\//, 'https://');
		if (/^https?:\/\//.test(url)) return url;
		const short = /^(?:github:)?([\w.-]+\/[\w.-]+)$/.exec(url);
		if (short) return `https://github.com/${short[1]}`;
	}
	return pkg.homepage ?? `https://www.npmjs.com/package/${pkg.name}`;
}

/**
 * Every package of the lockfile installed in node_modules/, dev dependencies
 * included: the site serves some of them (Pyodide). Optional packages for
 * other platforms are not installed, so they are not part of this build.
 */
export function installedPackages(dir) {
	const lock = JSON.parse(readFileSync(join(dir, 'package-lock.json'), 'utf8'));
	if (!lock.packages) throw new Error('package-lock.json has no "packages" (lockfileVersion 2 or later is needed)');
	const seen = new Map();
	for (const [location, entry] of Object.entries(lock.packages)) {
		if (!location || entry.link) continue;
		const path = join(dir, location);
		if (!existsSync(join(path, 'package.json'))) continue;
		const pkg = JSON.parse(readFileSync(join(path, 'package.json'), 'utf8'));
		const key = `${pkg.name}@${pkg.version}`;
		if (seen.has(key)) continue;
		const texts = readdirSync(path)
			.filter((name) => LICENSE_FILE.test(name) && statSync(join(path, name)).isFile())
			.sort()
			.map((name) => [name, cleanText(readFileSync(join(path, name), 'utf8'))])
			.filter(([, text]) => text);
		seen.set(key, { name: pkg.name, version: pkg.version, declared: declaredLicense(pkg), url: sourceUrl(pkg), texts });
	}
	return [...seen.values()].sort(byName);
}

// ---------------------------------------------------------------- Python wheels

/** The files of a zip archive (a wheel), as a map of name to a function that reads it. */
export function readZip(path) {
	const zip = readFileSync(path);
	let end = zip.length - 22;
	while (end >= 0 && zip.readUInt32LE(end) !== 0x06054b50) end--;
	if (end < 0) throw new Error(`${path} is not a zip archive`);
	const count = zip.readUInt16LE(end + 10);
	let pos = zip.readUInt32LE(end + 16);
	const files = new Map();
	for (let i = 0; i < count; i++) {
		if (zip.readUInt32LE(pos) !== 0x02014b50) throw new Error(`${path}: bad zip central directory`);
		const method = zip.readUInt16LE(pos + 10);
		const size = zip.readUInt32LE(pos + 20);
		const nameLength = zip.readUInt16LE(pos + 28);
		const extraLength = zip.readUInt16LE(pos + 30);
		const commentLength = zip.readUInt16LE(pos + 32);
		const offset = zip.readUInt32LE(pos + 42);
		const name = zip.toString('utf8', pos + 46, pos + 46 + nameLength);
		files.set(name, () => {
			const start = offset + 30 + zip.readUInt16LE(offset + 26) + zip.readUInt16LE(offset + 28);
			const data = zip.subarray(start, start + size);
			if (method === 0) return data;
			if (method === 8) return inflateRawSync(data);
			throw new Error(`${path}: ${name} uses zip compression method ${method}`);
		});
		pos += 46 + nameLength + extraLength + commentLength;
	}
	return files;
}

/** The header fields of a core-metadata file (METADATA), as name -> values. */
export function parseMetadata(text) {
	const fields = new Map();
	let last;
	for (const line of text.replace(/\r\n?/g, '\n').split('\n')) {
		if (line === '') break;
		if (/^[ \t]/.test(line) && last) {
			last.push(`${last.pop()}\n${line.trim()}`);
			continue;
		}
		const colon = line.indexOf(':');
		if (colon < 0) continue;
		const key = line.slice(0, colon).toLowerCase();
		if (!fields.has(key)) fields.set(key, []);
		last = fields.get(key);
		last.push(line.slice(colon + 1).trim());
	}
	return fields;
}

/**
 * The licence a wheel states, as .github/scripts/licenses.py reads it: its
 * PEP 639 expression, else a one-line `License` field, else its classifiers.
 */
export function wheelLicense(fields) {
	const first = (key) => fields.get(key)?.[0]?.trim() ?? '';
	if (first('license-expression')) return first('license-expression');
	const license = first('license');
	if (license && !license.includes('\n')) return license;
	const classifiers = (fields.get('classifier') ?? [])
		.filter((c) => c.startsWith('License ::'))
		.map((c) => c.split('::').at(-1).trim());
	if (classifiers.length) return classifiers.join(' AND ');
	return license.split('\n')[0];
}

/** A wheel's name, version, licence and the licence and NOTICE files it carries. */
export function wheelPackage(path) {
	const files = readZip(path);
	const metadata = [...files.keys()].find((name) => /^[^/]+\.dist-info\/METADATA$/.test(name));
	if (!metadata) throw new Error(`${path} has no .dist-info/METADATA`);
	const info = metadata.slice(0, -'METADATA'.length);
	const fields = parseMetadata(files.get(metadata)().toString('utf8'));
	const read = (name) => cleanText(files.get(name)().toString('utf8'));
	let texts = (fields.get('license-file') ?? [])
		.map((name) => [name, [`${info}licenses/${name}`, `${info}${name}`].find((f) => files.has(f))])
		.filter(([, file]) => file)
		.map(([name, file]) => [name, read(file)]);
	if (texts.length === 0) {
		texts = [...files.keys()]
			.filter((name) => name.startsWith(info) && LICENSE_FILE.test(posix.basename(name)))
			.sort()
			.map((name) => [name.slice(info.length), read(name)]);
	}
	const urls = Object.fromEntries(
		(fields.get('project-url') ?? []).map((entry) => {
			const [label, ...url] = entry.split(',');
			return [label.trim().toLowerCase(), url.join(',').trim()];
		}),
	);
	const url =
		['source', 'source code', 'repository', 'github', 'homepage', 'home'].map((k) => urls[k]).find(Boolean) ??
		fields.get('home-page')?.[0] ??
		'';
	const name = fields.get('name')?.[0] ?? '';
	return { name, version: fields.get('version')?.[0] ?? '', declared: wheelLicense(fields), url, texts: texts.filter(([, t]) => t) };
}

/** Every Python wheel the site serves (under public/), except MarketForge's own. */
export function servedWheels(dir) {
	const found = [];
	const walk = (path) => {
		if (!existsSync(path)) return;
		for (const name of readdirSync(path)) {
			const child = join(path, name);
			if (statSync(child).isDirectory()) walk(child);
			else if (name.endsWith('.whl') && !PROJECT_WHEEL.test(name)) found.push(child);
		}
	};
	walk(join(dir, 'public'));
	return found.map((path) => ({ ...wheelPackage(path), served: relative(join(dir, 'public'), path).split(sep).join('/') })).sort(byName);
}

// ---------------------------------------------------------------- policy

const normalizePython = (name) => name.toLowerCase().replace(/[-_.]+/g, '-');

/** The policy entry for a package: an exact key, else the longest matching `prefix*` key. */
export function policyEntry(rules, name, python = false) {
	const entries = rules.packages ?? {};
	const norm = python ? normalizePython : (n) => n;
	const exact = Object.keys(entries).find((key) => norm(key) === norm(name));
	if (exact) return [exact, entries[exact]];
	const matches = Object.keys(entries)
		.filter((key) => key.endsWith('*') && norm(name).startsWith(norm(key.slice(0, -1))))
		.sort((a, b) => b.length - a.length);
	return matches.length ? [matches[0], entries[matches[0]]] : [undefined, undefined];
}

/** Values a saved text's `from` URL can use, besides {version}: the CPython and Emscripten of Pyodide. */
export function templateValues(dir) {
	const lock = join(dir, 'node_modules', 'pyodide', 'pyodide-lock.json');
	if (!existsSync(lock)) return {};
	const { info } = JSON.parse(readFileSync(lock, 'utf8'));
	const emscripten = /^emscripten_(\d+)_(\d+)_(\d+)$/.exec(info?.platform ?? '');
	return { python: info?.python, emscripten: emscripten ? emscripten.slice(1).join('.') : undefined };
}

export const fillTemplate = (template, values) =>
	template.replace(/\{(\w+)\}/g, (match, key) => {
		if (values[key] === undefined) throw new Error(`${template}: no value for {${key}}`);
		return values[key];
	});

/** Checks one package; returns it with its accepted licence and texts, or throws. */
export function resolve(pkg, rules, { dir = websiteDir, python = false, section = 'packages', values = {} } = {}) {
	const [key, entry] = policyEntry(rules, pkg.name, python);
	const file = `${POLICY_FILE}${python ? ' (python)' : ''}`;
	const where = key ? `"${key}" in ${file}` : `an entry "${pkg.name}" in ${file} ${section}`;
	const id = `${pkg.name} ${pkg.version}`;
	let license = pkg.declared;
	if (entry) {
		if (entry.declared !== pkg.declared) {
			throw new Error(
				`${id} declares the licence '${pkg.declared}', but ${where} was reviewed for ` +
					`'${entry.declared}'. Read its licence, then update or remove the entry`,
			);
		}
		license = entry.license ?? license;
	}
	const allowed = [...rules.allowed, ...(entry?.allow ?? [])];
	let ok;
	try {
		ok = spdxAllowed(license, allowed, rules.exceptions ?? []);
	} catch {
		throw new Error(
			`${id} declares the licence '${pkg.declared}', which is not an SPDX expression. ` +
				`Read its licence and add ${where} with "declared" and "license"`,
		);
	}
	if (!ok) {
		throw new Error(
			`${id} is under '${license}', which the policy does not allow ` +
				`(allowed: ${[...new Set(allowed)].sort().join(', ')}). If that is not the SPDX ` +
				`identifier of its licence, read its licence and give the right one with "license" in ` +
				`${where}. Otherwise it needs a decision: replace it, or allow it for this package ` +
				`only with "allow"`,
		);
	}
	let texts = pkg.texts;
	if (entry?.texts?.length) {
		if (entry.version !== pkg.version) {
			throw new Error(
				`${id}: the licence texts ${where} adds were saved for version ${entry.version}. Run ` +
					'`npm run vendor-licenses` to fetch them for this version, then review and commit the change',
			);
		}
		const saved = entry.texts.map(({ file: path, from }) => {
			const full = join(dir, path);
			if (!existsSync(full)) throw new Error(`${id}: ${path} is missing; run \`npm run vendor-licenses\``);
			const url = fillTemplate(from, { ...values, version: pkg.version });
			return [`${posix.basename(path)} (from ${url})`, cleanText(readFileSync(full, 'utf8'))];
		});
		texts = [...texts, ...saved];
	}
	if (texts.length === 0 && !entry?.notServed) {
		throw new Error(
			`${id} ships no licence text. Save its upstream licence: add it to "texts" in ${where} ` +
				'and run `npm run vendor-licenses`. Or, if nothing of it reaches the site, say why with "notServed"',
		);
	}
	const url = entry?.source ? fillTemplate(entry.source, { ...values, version: pkg.version }) : pkg.url;
	return { ...pkg, license, texts, url, notServed: texts.length === 0 ? entry.notServed : undefined };
}

// ---------------------------------------------------------------- report

function table(packages) {
	const width = Math.max(7, ...packages.map((p) => p.name.length));
	const versionWidth = Math.max(7, ...packages.map((p) => p.version.length));
	return [
		`${'Package'.padEnd(width)}  ${'Version'.padEnd(versionWidth)}  Licence`,
		`${'-'.repeat(width)}  ${'-'.repeat(versionWidth)}  -------`,
		...packages.map((p) => `${p.name.padEnd(width)}  ${p.version.padEnd(versionWidth)}  ${p.license}`),
	];
}

function sections(packages) {
	const out = [];
	for (const p of packages) {
		out.push('', '', RULE, `${p.name} ${p.version}`, `Licence: ${p.license}`);
		if (p.license !== p.declared) out.push(`Declared as: ${p.declared}`);
		if (p.served) out.push(`Served as: ${p.served}`);
		if (p.url) out.push(`Source: ${p.url}`);
		out.push(RULE);
		if (p.notServed) out.push('', `No licence text is published with this package. ${p.notServed}`);
		for (const [name, text] of p.texts) out.push('', `----- ${name} -----`, '', text);
	}
	return out;
}

export function render(npm, python = []) {
	const out = [
		'MarketForge website: third-party licences',
		RULE,
		'',
		'This website is built from the npm packages below (website/package.json, as',
		'website/package-lock.json locks it). Code, styles and fonts from some of them',
		'are part of the files the site serves: Astro, Starlight, Expressive Code,',
		'Pagefind, the DM Sans and DM Mono fonts (SIL Open Font License 1.1), and',
		"Pyodide, the playground's Python runtime (CPython and Emscripten). The others",
		'build the site and are listed so that nothing the site serves is left out.',
	];
	if (python.length) {
		out.push(
			'',
			'The playground also serves the Python wheels listed second, unmodified, as',
			'Pyodide builds them. Where a wheel lacks texts its upstream release has, they',
			'are added from that release, at the same version.',
		);
	}
	out.push(
		'',
		"MarketForge's own content and code are under the Apache License 2.0:",
		'https://github.com/DamienReichhart/MarketForge/blob/main/LICENSE',
		'',
		'Generated by website/scripts/third-party-licenses.mjs on every build; do not edit.',
		'',
		'',
		'npm packages',
		'------------',
		'',
		...table(npm),
	);
	if (python.length) out.push('', '', 'Python packages served by the playground', '----------------------------------------', '', ...table(python));
	out.push(...sections(npm), ...sections(python));
	return `${out.join('\n')}\n`;
}

// ---------------------------------------------------------------- commands

const loadPolicy = (dir) => JSON.parse(readFileSync(join(dir, POLICY_FILE), 'utf8'));

function* checked(dir, policy) {
	const values = templateValues(dir);
	const python = policy.python ?? { allowed: [], packages: {} };
	for (const pkg of installedPackages(dir)) yield [pkg, policy, { dir, values }];
	for (const pkg of servedWheels(dir)) yield [pkg, python, { dir, values, python: true, section: '"python.packages"' }];
}

export function main(dir = websiteDir) {
	const policy = loadPolicy(dir);
	const npm = [];
	const python = [];
	const errors = [];
	const used = { npm: new Set(), python: new Set() };
	for (const [pkg, rules, options] of checked(dir, policy)) {
		used[options.python ? 'python' : 'npm'].add(policyEntry(rules, pkg.name, options.python)[0]);
		try {
			(options.python ? python : npm).push(resolve(pkg, rules, options));
		} catch (error) {
			errors.push(error.message);
		}
	}
	if (npm.length === 0) errors.push('no installed packages: run `npm ci` first');
	for (const [kind, rules] of [['npm', policy], ['python', policy.python ?? {}]]) {
		for (const key of Object.keys(rules.packages ?? {})) {
			if (!used[kind].has(key)) console.warn(`warning: ${POLICY_FILE}: ${kind} entry "${key}" matches no package; remove it if it is gone`);
		}
	}
	if (errors.length) {
		for (const error of errors) console.error(`error: ${error}`);
		console.error(`${errors.length} package(s) failed the licence policy (${POLICY_FILE}).`);
		process.exitCode = 1;
		return;
	}
	mkdirSync(join(dir, 'public'), { recursive: true });
	writeFileSync(join(dir, OUTPUT), render(npm, python));
	console.log(`Wrote ${OUTPUT} (${npm.length} npm packages, ${python.length} Python wheels)`);
}

/**
 * Fetches every text the policy saves (`texts`) for the version installed or
 * served now, writes it to its file and records that version. Review the diff.
 */
export async function vendor(dir = websiteDir, fetchText = defaultFetch) {
	const policy = loadPolicy(dir);
	const versions = new Map();
	for (const [pkg, rules, options] of checked(dir, policy)) {
		const [, entry] = policyEntry(rules, pkg.name, options.python);
		if (!entry?.texts?.length) continue;
		if (!versions.has(entry)) versions.set(entry, new Set());
		versions.get(entry).add(pkg.version);
	}
	const values = templateValues(dir);
	for (const [entry, found] of versions) {
		if (found.size > 1) throw new Error(`one entry covers several versions (${[...found].join(', ')}); split it`);
		const [version] = found;
		for (const { file, from } of entry.texts) {
			const url = fillTemplate(from, { ...values, version });
			const text = cleanText(await fetchText(url));
			if (!text) throw new Error(`${url} is empty`);
			mkdirSync(dirname(join(dir, file)), { recursive: true });
			writeFileSync(join(dir, file), `${text}\n`);
			console.log(`saved ${file} from ${url}`);
		}
		entry.version = version;
	}
	writeFileSync(join(dir, POLICY_FILE), `${JSON.stringify(policy, null, '\t')}\n`);
}

async function defaultFetch(url) {
	const response = await fetch(url);
	if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
	return response.text();
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
	if (process.argv.includes('--vendor')) {
		vendor().catch((error) => {
			console.error(`error: ${error.message}`);
			process.exitCode = 1;
		});
	} else {
		main();
	}
}
