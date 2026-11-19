// Fails when a page of the built site links to a page or file of the site
// that does not exist. Run after `astro build`.

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const dist = fileURLToPath(new URL('../dist/', import.meta.url));
const BASE = '/MarketForge/';

function* htmlFiles(dir) {
	for (const name of readdirSync(dir)) {
		const path = join(dir, name);
		if (statSync(path).isDirectory()) yield* htmlFiles(path);
		else if (name.endsWith('.html')) yield path;
	}
}

const broken = [];
let checked = 0;
for (const file of htmlFiles(dist)) {
	const page = BASE + relative(dist, file).split(sep).join('/').replace(/index\.html$/, '');
	const html = readFileSync(file, 'utf8');
	for (const [, href] of html.matchAll(/\shref="([^"]*)"/g)) {
		if (!href || /^(?:[a-z]+:|#|\/\/)/i.test(href)) continue;
		const url = new URL(href, `https://site${page}`);
		checked++;
		if (!url.pathname.startsWith(BASE)) {
			broken.push(`${page}: ${href} is outside ${BASE}`);
			continue;
		}
		const target = join(dist, decodeURIComponent(url.pathname.slice(BASE.length)));
		if (!existsSync(target) || (statSync(target).isDirectory() && !existsSync(join(target, 'index.html')))) {
			broken.push(`${page}: ${href}`);
		}
	}
}

if (broken.length) {
	console.error(`${broken.length} broken internal link(s):\n${broken.join('\n')}`);
	process.exit(1);
}
console.log(`${checked} internal links checked, none broken`);
