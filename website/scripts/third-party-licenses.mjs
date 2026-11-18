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
// Packages that compile third-party code into what the site serves (Pyodide,
// Pagefind) list it as components, resolved from upstream's own build files
// and lockfiles by vendor-licenses.mjs into a manifest under licenses/. For
// a WebAssembly binary, every symbol it exports must belong to a component or
// to the reviewed list of C runtime symbols, so a library linked in without
// its licence fails the build. Network access is only needed by
// vendor-licenses.mjs; this script runs offline.

import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, posix, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { readZip, wasmExports } from './archives.mjs';

export const websiteDir = join(dirname(fileURLToPath(import.meta.url)), '..');
export const POLICY_FILE = 'license-policy.json';
const OUTPUT = join('public', 'third-party-licenses.txt');
export const LICENSE_FILE = /^(licen[cs]e|copying|notice|copyright|ofl)([-._ ].*)?$/i;
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
		seen.set(key, { name: pkg.name, version: pkg.version, declared: declaredLicense(pkg), url: sourceUrl(pkg), texts, dir: path });
	}
	return [...seen.values()].sort(byName);
}

// ---------------------------------------------------------------- Python wheels

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
	const files = readZip(readFileSync(path), path);
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
	const components = entry?.components ? loadComponents(pkg, entry, rules, { dir, id, where }) : [];
	const url = entry?.source ? fillTemplate(entry.source, { ...values, version: pkg.version }) : pkg.url;
	return { ...pkg, license, texts, url, components, notServed: texts.length === 0 ? entry.notServed : undefined };
}

/**
 * The third-party components compiled into a package's served files, from the
 * manifest vendor-licenses.mjs wrote; each is checked like a package. With a
 * `binary`, every symbol the WebAssembly exports must be claimed.
 */
function loadComponents(pkg, entry, rules, { dir, id, where }) {
	const spec = entry.components;
	const vendorHint = '`npm run vendor-licenses`';
	const manifestPath = join(dir, spec.manifest);
	if (!existsSync(manifestPath)) throw new Error(`${id}: ${spec.manifest} is missing; run ${vendorHint}`);
	const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
	if (manifest.version !== pkg.version) {
		throw new Error(
			`${id}: the components in ${spec.manifest} were resolved for version ${manifest.version}. Run ` +
				`${vendorHint} to resolve them for this version, then review and commit the change`,
		);
	}
	const allowed = [...rules.allowed, ...(entry.allow ?? [])];
	// Symbol patterns are policy, not resolved data: read them from the recipes.
	const symbols = new Map(spec.sources.filter((r) => r.name && r.symbols).map((r) => [r.name, r.symbols]));
	const components = manifest.components.map((manifestEntry) => {
		const c = { ...manifestEntry, symbols: symbols.get(manifestEntry.name) };
		const cid = `${id}: its component ${c.name} ${c.version}`;
		let ok;
		try {
			ok = spdxAllowed(c.license, allowed, rules.exceptions ?? []);
		} catch {
			throw new Error(`${cid} declares the licence '${c.license}', which is not an SPDX expression. Give it in its recipe in ${where}`);
		}
		if (!ok) {
			throw new Error(
				`${cid} is under '${c.license}', which the policy does not allow for ${pkg.name}. Replace the ` +
					`package, or allow it for this package with "allow" in ${where}, with the reason`,
			);
		}
		if (!c.texts?.length) throw new Error(`${cid} has no licence text; run \`npm run vendor-licenses\`, which says what to do`);
		const texts = c.texts.map(({ file, from }) => {
			if (!existsSync(join(dir, file))) throw new Error(`${cid}: ${file} is missing; run ${vendorHint}`);
			return [`${posix.basename(file)} (from ${from})`, cleanText(readFileSync(join(dir, file), 'utf8'))];
		});
		return { ...c, texts };
	});
	if (spec.binary) checkBinary(pkg, spec.binary, components, { dir, id, where });
	return components;
}

/**
 * Every symbol a WebAssembly binary of the package exports must belong to one
 * of its components (their `symbols` pattern), to the package's own code
 * (`ownSymbols`), or to the reviewed C runtime list (`runtimeSymbols`: musl,
 * compiler-rt, Emscripten, whose licences are components). A component no
 * export belongs to is not in the binary any more, and fails too.
 */
export function checkBinary(pkg, binary, components, { dir, id, where }) {
	const exports = wasmExports(readFileSync(join(pkg.dir, binary.file)));
	const runtime = new Set(
		readFileSync(join(dir, binary.runtimeSymbols), 'utf8')
			.split('\n')
			.map((line) => line.trim())
			.filter((line) => line && !line.startsWith('#')),
	);
	const own = new RegExp(binary.ownSymbols);
	const claimers = components.filter((c) => c.symbols).map((c) => [c, new RegExp(c.symbols)]);
	const unclaimed = exports.filter((name) => !own.test(name) && !runtime.has(name) && !claimers.some(([, re]) => re.test(name)));
	const errors = [];
	if (unclaimed.length) {
		const sample = [...new Set(unclaimed)].sort().slice(0, 40).join(' ');
		errors.push(
			`${id}: ${binary.file} exports ${unclaimed.length} symbol(s) no component claims: ${sample}. Find the ` +
				`library they come from (the upstream build files), add a recipe for it with its licence to ` +
				`"components.sources" in ${where} and run \`npm run vendor-licenses\`. Only if they are C runtime ` +
				`(musl, compiler-rt, Emscripten) add them to ${binary.runtimeSymbols}`,
		);
	}
	for (const [c, re] of claimers) {
		if (!exports.some((name) => re.test(name))) {
			errors.push(`${id}: no symbol of ${binary.file} matches the component ${c.name} (${c.symbols}); is it still linked in?`);
		}
	}
	const stale = [...runtime].filter((name) => !exports.includes(name));
	if (stale.length) console.warn(`warning: ${binary.runtimeSymbols}: ${stale.length} symbol(s) are not exported any more (${stale.slice(0, 10).join(' ')}); remove them`);
	if (errors.length) throw new Error(errors.join('\n'));
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
		if (p.components?.length) {
			out.push('', `Compiled into ${p.name}'s served files: ${p.components.length} components.`);
			for (const c of p.components) {
				out.push('', '-'.repeat(79), `${p.name} component: ${c.name} ${c.version}`, `Licence: ${c.license}`);
				if (c.url) out.push(`Source: ${c.url}`);
				if (c.via) out.push(`Through: ${c.via}`);
				out.push('-'.repeat(79));
				for (const [name, text] of c.texts) out.push('', `----- ${name} -----`, '', text);
			}
		}
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

export const loadPolicy = (dir) => JSON.parse(readFileSync(join(dir, POLICY_FILE), 'utf8'));

export function* checked(dir, policy) {
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

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main();
