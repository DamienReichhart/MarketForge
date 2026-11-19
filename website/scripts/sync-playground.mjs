// Puts what the playground runs into public/playground/, so the site serves
// it itself and visitors contact no third party (docs/adr/0015). Runs before
// every dev, check and build, after sync-content.mjs.
//
//   node_modules/pyodide/{pyodide.mjs,...}  -> public/playground/pyodide/
//   the wheels of NEEDED and their dependencies, downloaded once from
//   Pyodide's CDN into .cache/pyodide/ and checked against pyodide-lock.json
//                                          -> public/playground/pyodide/
//   the MarketForge wheel: ../dist/marketforge-<version>-py3-none-any.whl
//   when CI built it, else built here with pip
//                                          -> public/playground/
//   src/playground/runner.py               -> public/playground/runner.py
//   what the page needs to know about them -> public/playground/manifest.json
//
// The Pyodide version is the exact `pyodide` devDependency in package.json.

import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const websiteDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const repoDir = join(websiteDir, '..');
const pyodideDir = join(websiteDir, 'node_modules', 'pyodide');
const cacheDir = join(websiteDir, '.cache', 'pyodide');
const outDir = join(websiteDir, 'public', 'playground');
const outPyodide = join(outDir, 'pyodide');

/** What `import marketforge` needs in Pyodide (Numba is not one: ADR 0015). */
const NEEDED = ['numpy', 'pandas', 'pyarrow', 'threadpoolctl', 'tzdata'];
const RUNTIME = ['pyodide.mjs', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json'];

const sha256 = (path) => createHash('sha256').update(readFileSync(path)).digest('hex');
const megabytes = (bytes) => Math.round(bytes / 1e5) / 10;

const pyodideVersion = JSON.parse(readFileSync(join(pyodideDir, 'package.json'), 'utf8')).version;
const lock = JSON.parse(readFileSync(join(pyodideDir, 'pyodide-lock.json'), 'utf8'));

/** NEEDED and everything it depends on, by Pyodide package name. */
function closure(names) {
	const seen = new Set();
	const visit = (name) => {
		const key = name.toLowerCase().replace(/[_.]/g, '-');
		if (seen.has(key)) return;
		if (!lock.packages[key]) throw new Error(`Pyodide ${pyodideVersion} has no package "${name}"`);
		seen.add(key);
		lock.packages[key].depends.forEach(visit);
	};
	names.forEach(visit);
	return [...seen].sort();
}

/** A Pyodide wheel, from the cache or the CDN, refused unless its hash is the lock file's. */
async function wheel(name) {
	const { file_name: file, sha256: expected } = lock.packages[name];
	const cached = join(cacheDir, file);
	if (!existsSync(cached) || sha256(cached) !== expected) {
		const url = `https://cdn.jsdelivr.net/pyodide/v${pyodideVersion}/full/${file}`;
		const response = await fetch(url);
		if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
		const bytes = Buffer.from(await response.arrayBuffer());
		const actual = createHash('sha256').update(bytes).digest('hex');
		if (actual !== expected) throw new Error(`${file}: sha256 ${actual}, the lock file says ${expected}`);
		mkdirSync(cacheDir, { recursive: true });
		writeFileSync(cached, bytes);
	}
	return cached;
}

/** The MarketForge wheel of this checkout: CI's if it built one, else a fresh build. */
function marketforgeWheel() {
	const version = /^version = "([^"]+)"/m.exec(readFileSync(join(repoDir, 'pyproject.toml'), 'utf8'))[1];
	const file = `marketforge-${version}-py3-none-any.whl`;
	const built = join(repoDir, 'dist', file);
	if (existsSync(built)) return { version, path: built };
	const buildDir = join(websiteDir, '.cache', 'wheel');
	rmSync(buildDir, { recursive: true, force: true });
	try {
		execFileSync('python3', ['-m', 'pip', 'wheel', '--no-deps', '--quiet', '--wheel-dir', buildDir, repoDir], {
			stdio: ['ignore', 'ignore', 'inherit'],
		});
	} catch {
		throw new Error(`could not build ${file}: build it with \`pip wheel --no-deps -w dist .\` from the repository root`);
	}
	return { version, path: join(buildDir, file) };
}

rmSync(outDir, { recursive: true, force: true });
mkdirSync(outPyodide, { recursive: true });
for (const file of RUNTIME) copyFileSync(join(pyodideDir, file), join(outPyodide, file));
const packages = closure(NEEDED);
for (const name of packages) copyFileSync(await wheel(name), join(outPyodide, lock.packages[name].file_name));

const marketforge = marketforgeWheel();
const wheelFile = marketforge.path.split(/[\\/]/).at(-1);
copyFileSync(marketforge.path, join(outDir, wheelFile));
copyFileSync(join(websiteDir, 'src', 'playground', 'runner.py'), join(outDir, 'runner.py'));

const total = (dir) =>
	readdirSync(dir).reduce((sum, file) => {
		const path = join(dir, file);
		return sum + (statSync(path).isDirectory() ? total(path) : statSync(path).size);
	}, 0);
const manifest = {
	marketforge: marketforge.version,
	wheel: wheelFile,
	pyodide: pyodideVersion,
	packages,
	downloadMB: megabytes(total(outDir)),
};
writeFileSync(join(outDir, 'manifest.json'), `${JSON.stringify(manifest, null, '\t')}\n`);
console.log(
	`synced the playground: MarketForge ${manifest.marketforge}, Pyodide ${pyodideVersion}, ` +
		`${packages.length} packages, ${manifest.downloadMB} MB`,
);
