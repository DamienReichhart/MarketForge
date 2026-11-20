// Fails when a page of the built site links to an external page that is
// gone (404 or 410) or whose host no longer resolves. Run after
// `astro build`; CI runs it weekly, not on pull requests, because a remote
// site's state is not a property of a change.
//
// Only definite breakage fails. A site that refuses robots (401, 403, 429),
// errs (5xx) or times out is reported as unverified: those come and go, and
// failing on them would train everyone to ignore the alert.

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const dist = fileURLToPath(new URL('../dist/', import.meta.url));
const TIMEOUT_MS = 20_000;
const ATTEMPTS = 3;
const PER_HOST = 2; // concurrent requests to one host
const USER_AGENT = 'Mozilla/5.0 (compatible; link-check; +https://github.com/DamienReichhart/marketforge)';

function* htmlFiles(dir) {
	for (const name of readdirSync(dir)) {
		const path = join(dir, name);
		if (statSync(path).isDirectory()) yield* htmlFiles(path);
		else if (name.endsWith('.html')) yield path;
	}
}

/** url (without fragment) -> pages that link to it */
const links = new Map();
for (const file of htmlFiles(dist)) {
	const page = '/' + relative(dist, file).split(sep).join('/').replace(/index\.html$/, '');
	const html = readFileSync(file, 'utf8');
	for (const [, raw] of html.matchAll(/<a\s[^>]*?href="(https?:\/\/[^"]+)"/gi)) {
		const url = new URL(raw.replaceAll('&amp;', '&'));
		url.hash = '';
		const key = url.href;
		if (!links.has(key)) links.set(key, new Set());
		links.get(key).add(page);
	}
}

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

/** @returns {Promise<{ ok: boolean, definite: boolean, detail: string }>} */
async function check(url) {
	let last = { ok: false, definite: false, detail: 'not checked' };
	for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
		for (const method of ['HEAD', 'GET']) {
			try {
				const response = await fetch(url, {
					method,
					redirect: 'follow',
					headers: { 'user-agent': USER_AGENT, accept: 'text/html,*/*' },
					signal: AbortSignal.timeout(TIMEOUT_MS),
				});
				await response.body?.cancel();
				if (response.ok) return { ok: true, definite: true, detail: String(response.status) };
				last = {
					ok: false,
					definite: response.status === 404 || response.status === 410,
					detail: `HTTP ${response.status}`,
				};
				// Some servers answer HEAD wrongly (404, 405, 403): ask again with GET.
				if (method === 'HEAD') continue;
				if (last.definite || ![429, 500, 502, 503, 504].includes(response.status)) return last;
			} catch (error) {
				const code = error?.cause?.code ?? error?.name ?? 'error';
				last = { ok: false, definite: code === 'ENOTFOUND', detail: code };
				if (last.definite) return last;
				break; // a network error: retry the whole attempt after a pause
			}
		}
		await sleep(2_000 * attempt);
	}
	return last;
}

// A small pool per host: polite to each site, still parallel across sites.
const byHost = new Map();
for (const url of links.keys()) {
	const host = new URL(url).host;
	if (!byHost.has(host)) byHost.set(host, []);
	byHost.get(host).push(url);
}
const results = new Map();
await Promise.all(
	[...byHost.values()].flatMap((urls) =>
		Array.from({ length: PER_HOST }, async (_, worker) => {
			for (let i = worker; i < urls.length; i += PER_HOST) {
				results.set(urls[i], await check(urls[i]));
			}
		}),
	),
);

const broken = [];
const unverified = [];
for (const [url, result] of results) {
	if (result.ok) continue;
	const pages = [...links.get(url)].sort();
	const line = `${url} (${result.detail}), linked from ${pages.slice(0, 3).join(', ')}${pages.length > 3 ? ` and ${pages.length - 3} more` : ''}`;
	(result.definite ? broken : unverified).push(line);
}

const inActions = Boolean(process.env.GITHUB_ACTIONS);
for (const line of unverified) console.log(inActions ? `::warning title=Unverified link::${line}` : `unverified: ${line}`);
for (const line of broken) console.log(inActions ? `::error title=Broken link::${line}` : `BROKEN: ${line}`);
console.log(
	`${results.size} external links on ${byHost.size} hosts: ${broken.length} broken, ${unverified.length} unverified`,
);
process.exit(broken.length ? 1 : 0);
