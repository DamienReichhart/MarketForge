// Writes public/third-party-licenses.txt: the licence and NOTICE texts of
// every package the website is built from, so the site serves the notices of
// the third-party code, styles and fonts it ships (Astro, Starlight, Expressive
// Code, Pagefind, DM Sans, DM Mono). Runs before every dev, check and build
// (`npm run sync`), from the installed production tree of package-lock.json,
// so it cannot fall out of date.
//
// Every package's licence is checked against license-policy.json. The build
// fails when a licence is not allowed or is not an SPDX expression, when a
// package changes the licence its policy entry was reviewed for, and when a
// package ships no licence text and the policy gives none.

import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, posix } from 'node:path';
import { fileURLToPath } from 'node:url';

const websiteDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const POLICY_FILE = 'license-policy.json';
const OUTPUT = join('public', 'third-party-licenses.txt');
const LICENSE_FILE = /^(licen[cs]e|copying|notice|copyright|ofl)([-._ ].*)?$/i;
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

// ---------------------------------------------------------------- packages

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

export function cleanText(text) {
	return text
		.replace(/\r\n?/g, '\n')
		.split('\n')
		.map((line) => line.trimEnd())
		.join('\n')
		.replace(/^\n+|\n+$/g, '');
}

/**
 * The production packages installed from the lockfile: every entry that is not
 * dev-only and is on disk (optional packages for other platforms are not
 * installed, so they are not part of this build).
 */
export function installedPackages(dir) {
	const lock = JSON.parse(readFileSync(join(dir, 'package-lock.json'), 'utf8'));
	if (!lock.packages) throw new Error('package-lock.json has no "packages" (lockfileVersion 2 or later is needed)');
	const seen = new Map();
	for (const [location, entry] of Object.entries(lock.packages)) {
		if (!location || entry.dev || entry.link) continue;
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
		seen.set(key, {
			name: pkg.name,
			version: pkg.version,
			declared: declaredLicense(pkg),
			url: sourceUrl(pkg),
			texts,
		});
	}
	return [...seen.values()].sort((a, b) =>
		a.name === b.name ? a.version.localeCompare(b.version) : a.name < b.name ? -1 : 1,
	);
}

/** The policy entry for a package: an exact key, else the longest matching `scope/prefix-*` key. */
export function policyEntry(policy, name) {
	const entries = policy.packages ?? {};
	if (entries[name]) return [name, entries[name]];
	const matches = Object.keys(entries)
		.filter((key) => key.endsWith('*') && name.startsWith(key.slice(0, -1)))
		.sort((a, b) => b.length - a.length);
	return matches.length ? [matches[0], entries[matches[0]]] : [undefined, undefined];
}

/** Checks one package; returns it with its accepted licence and texts, or throws. */
export function resolve(pkg, policy, dir = websiteDir) {
	const [key, entry] = policyEntry(policy, pkg.name);
	const where = key ? `"${key}" in ${POLICY_FILE}` : `an entry "${pkg.name}" in ${POLICY_FILE}`;
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
	const allowed = [...policy.allowed, ...(entry?.allow ?? [])];
	let ok;
	try {
		ok = spdxAllowed(license, allowed, policy.exceptions ?? []);
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
	if (texts.length === 0 && entry?.text) {
		texts = [[posix.basename(entry.text), cleanText(readFileSync(join(dir, entry.text), 'utf8'))]];
	}
	if (texts.length === 0 && !entry?.notServed) {
		throw new Error(
			`${id} ships no licence text. Save its upstream licence in licenses/ and point ` +
				`${where} at it ("text"), or, if nothing of it reaches the site, say why ("notServed")`,
		);
	}
	return { ...pkg, license, texts, notServed: texts.length === 0 ? entry.notServed : undefined };
}

// ---------------------------------------------------------------- report

export function render(packages) {
	const width = Math.max(7, ...packages.map((p) => p.name.length));
	const versionWidth = Math.max(7, ...packages.map((p) => p.version.length));
	const out = [
		'MarketForge website: third-party licences',
		RULE,
		'',
		'This website is built from the npm packages below (the production',
		'dependency tree of website/package.json, as website/package-lock.json',
		'locks it). Code, styles and fonts from some of them are part of the files',
		'the site serves: Astro, Starlight, Expressive Code, Pagefind, and the DM Sans',
		'and DM Mono fonts (SIL Open Font License 1.1). The others build the site and',
		'are listed so that nothing the site serves is left out.',
		'',
		"MarketForge's own content and code are under the Apache License 2.0:",
		'https://github.com/DamienReichhart/MarketForge/blob/main/LICENSE',
		'',
		'Generated by website/scripts/third-party-licenses.mjs on every build; do not edit.',
		'',
		'',
		`${'Package'.padEnd(width)}  ${'Version'.padEnd(versionWidth)}  Licence`,
		`${'-'.repeat(width)}  ${'-'.repeat(versionWidth)}  -------`,
		...packages.map((p) => `${p.name.padEnd(width)}  ${p.version.padEnd(versionWidth)}  ${p.license}`),
	];
	for (const p of packages) {
		out.push('', '', RULE, `${p.name} ${p.version}`, `Licence: ${p.license}`);
		if (p.license !== p.declared) out.push(`Declared as: ${p.declared}`);
		out.push(`Source: ${p.url}`, RULE);
		if (p.notServed) out.push('', `No licence text is published with this package. ${p.notServed}`);
		for (const [name, text] of p.texts) out.push('', `----- ${name} -----`, '', text);
	}
	return `${out.join('\n')}\n`;
}

export function main(dir = websiteDir) {
	const policy = JSON.parse(readFileSync(join(dir, POLICY_FILE), 'utf8'));
	const packages = installedPackages(dir);
	if (packages.length === 0) throw new Error('no installed packages: run `npm ci` first');
	const resolved = [];
	const errors = [];
	for (const pkg of packages) {
		try {
			resolved.push(resolve(pkg, policy, dir));
		} catch (error) {
			errors.push(error.message);
		}
	}
	const used = new Set(packages.map((p) => policyEntry(policy, p.name)[0]).filter(Boolean));
	for (const key of Object.keys(policy.packages ?? {})) {
		if (!used.has(key)) console.warn(`warning: ${POLICY_FILE}: "${key}" matches no installed package; remove it if it is gone`);
	}
	if (errors.length) {
		for (const error of errors) console.error(`error: ${error}`);
		console.error(`${errors.length} package(s) failed the licence policy (${POLICY_FILE}).`);
		process.exitCode = 1;
		return;
	}
	writeFileSync(join(dir, OUTPUT), render(resolved));
	console.log(`Wrote ${OUTPUT} (${resolved.length} packages)`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main();
