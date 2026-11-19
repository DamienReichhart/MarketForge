// An Astro integration that checks, on every build, the `notServed` claims of
// license-policy.json: a package that ships no licence text is exempt from the
// third-party licences only because nothing of it reaches the site. The build
// fails if anything of such a package does:
//
//   - a module of it is bundled into the scripts the browser loads (the client
//     build), or a style, font, image or WebAssembly file of it is emitted by
//     either build;
//   - a file of the built site is a byte-for-byte copy of one of its files
//     (something copied to public/ or into dist/ without the bundler).
//
// The server build's scripts are not served (they render the HTML at build
// time), so packages used only there are not counted as served.

import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { installedPackages, loadPolicy, POLICY_FILE, policyEntry, websiteDir } from './third-party-licenses.mjs';

const ASSET = /\.(css|woff2?|ttf|otf|eot|svg|png|jpe?g|gif|webp|avif|ico|wasm)$/i;
// Smaller files (an empty file, `{}`) say nothing about where they come from.
const MIN_COPY_BYTES = 256;

/** The npm package a file belongs to: the nearest package.json with a name, inside node_modules. */
export function packageOf(file, root = websiteDir) {
	const path = resolve(root, file.replace(/^\0+/, '').split('?')[0]);
	if (!path.split(sep).includes('node_modules')) return undefined;
	for (let dir = dirname(path); dir.split(sep).includes('node_modules'); dir = dirname(dir)) {
		const manifest = join(dir, 'package.json');
		if (!existsSync(manifest)) continue;
		try {
			const { name } = JSON.parse(readFileSync(manifest, 'utf8'));
			if (name) return name;
		} catch {
			// Not a package manifest; keep looking up.
		}
	}
	return undefined;
}

/** The installed packages license-policy.json says are not served, with their directories. */
export function notServedPackages(dir = websiteDir) {
	const policy = loadPolicy(dir);
	return installedPackages(dir).filter((pkg) => policyEntry(policy, pkg.name)[1]?.notServed);
}

function* files(dir) {
	for (const name of readdirSync(dir)) {
		const path = join(dir, name);
		const stat = statSync(path);
		if (stat.isDirectory()) yield* files(path);
		else if (stat.isFile()) yield [path, stat.size];
	}
}

const digest = (path) => createHash('sha256').update(readFileSync(path)).digest('hex');

/** Files of the built site that are byte-for-byte copies of a file of one of `packages`. */
export function copiedFiles(siteDir, packages) {
	const known = new Map(); // size -> [[path, package]]
	for (const pkg of packages) {
		for (const [path, size] of files(pkg.dir)) {
			if (size < MIN_COPY_BYTES) continue;
			if (!known.has(size)) known.set(size, []);
			known.get(size).push([path, pkg.name]);
		}
	}
	const copies = [];
	for (const [path, size] of files(siteDir)) {
		const candidates = known.get(size);
		if (!candidates) continue;
		const hash = digest(path);
		for (const [source, name] of candidates) if (digest(source) === hash) copies.push([relative(siteDir, path), name]);
	}
	return copies;
}

export default function servedPackages() {
	const sources = new Set();
	// Astro builds with Vite's environments: one plugin sees the client build
	// (what the browser loads) and the server ones (prerender, ssr).
	const plugin = {
		name: 'served-packages',
		generateBundle(_, bundle) {
			const client = this.environment?.name === 'client';
			for (const output of Object.values(bundle)) {
				if (output.type === 'chunk') {
					if (client) for (const id of output.moduleIds ?? Object.keys(output.modules ?? {})) sources.add(id);
				} else {
					for (const name of output.originalFileNames ?? []) sources.add(name);
				}
			}
			// Styles and fonts can come out of the server build too.
			for (const id of this.getModuleIds()) if (ASSET.test(id.split('?')[0])) sources.add(id);
		},
	};
	return {
		name: 'served-packages',
		hooks: {
			'astro:build:setup': ({ vite }) => {
				if (!vite.plugins?.includes(plugin)) vite.plugins = [...(vite.plugins ?? []), plugin];
			},
			'astro:build:done': ({ dir, logger }) => {
				const served = new Set([...sources].map((id) => packageOf(id)).filter(Boolean));
				const exempt = notServedPackages();
				const errors = exempt
					.filter((pkg) => served.has(pkg.name))
					.map((pkg) => `${pkg.name} is bundled into the site, but ${POLICY_FILE} says it is not served ("notServed")`);
				for (const [file, name] of copiedFiles(fileURLToPath(dir), exempt)) {
					errors.push(`${file} is a copy of a file of ${name}, which ${POLICY_FILE} says is not served ("notServed")`);
				}
				if (errors.length) {
					throw new Error(
						`${errors.join('\n')}\nIts licence text must ship with the site: save its upstream licence in licenses/ ` +
							'with "texts" instead of "notServed" (see the comment of license-policy.json).',
					);
				}
				if (!served.has('@astrojs/starlight')) {
					throw new Error('served-packages saw no Starlight module in the client build: the check itself is broken');
				}
				logger.info(
					`${served.size} npm packages reach the site (${[...served].sort().join(', ')}); none of the ${exempt.length} marked notServed does`,
				);
			},
		},
	};
}
