// Copies the repository's own Markdown into the docs site, so the changelog,
// the glossary and the architecture decision records have a single source of
// truth: the files at the repository root. Runs before every dev and build.
//
//   CHANGELOG.md   -> src/content/docs/changelog.md
//   GLOSSARY.md    -> src/content/docs/docs/reference/glossary.md
//   docs/adr/*.md  -> src/content/docs/docs/adr/*.md
//   docs/brand/README.md -> src/content/docs/docs/brand.md
//   docs/brand/assets/*  -> public/brand/*
//
// Relative links are rewritten: links to synced files point to their page on
// the site, any other repository path points to the file on GitHub.

import { copyFileSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, posix, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const websiteDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const repoDir = join(websiteDir, '..');
const contentDir = join(websiteDir, 'src', 'content', 'docs');

const REPO_URL = 'https://github.com/DamienReichhart/marketforge';
const BRANCH = 'main';

/**
 * Page of the site (relative to its root, e.g. `changelog/`) where a
 * repository file is published, or undefined if it is not.
 */
function sitePath(repoPath) {
	if (repoPath === 'CHANGELOG.md') return 'changelog/';
	if (repoPath === 'GLOSSARY.md') return 'docs/reference/glossary/';
	if (repoPath === 'docs/brand/README.md') return 'docs/brand/';
	const adr = /^docs\/adr\/([^/]+)\.md$/.exec(repoPath);
	if (adr) return `docs/adr/${adr[1].toLowerCase()}/`;
	return undefined;
}

/** A link from one page of the site to another, relative so it works under any base path. */
function pageLink(fromPage, toPage) {
	const link = posix.relative(fromPage, toPage);
	return link ? `${link}/` : './';
}

/**
 * Rewrites the relative Markdown links of a file found at `sourcePath`
 * (repository-relative) and published on the site at `page`.
 */
function rewriteLinks(markdown, sourcePath, page = sitePath(sourcePath)) {
	const sourceDir = posix.dirname(sourcePath);
	return markdown.replace(/\]\(([^)\s]+)\)/g, (match, target) => {
		if (/^([a-z]+:|#|\/)/i.test(target)) return match;
		const [path, anchor] = target.split('#');
		const resolved = posix.normalize(posix.join(sourceDir, path)).replace(/\/$/, '');
		const hash = anchor ? `#${anchor}` : '';
		const asset = /^docs\/brand\/assets\/([^/]+)$/.exec(resolved);
		if (asset) return `](${posix.relative(page, `brand/${asset[1]}`)})`;
		const published = sitePath(resolved);
		if (published) return `](${pageLink(page, published)}${hash})`;
		const kind = /\.[a-z0-9]+$/i.test(resolved) ? 'blob' : 'tree';
		return `](${REPO_URL}/${kind}/${BRANCH}/${resolved}${hash})`;
	});
}

/** Splits off the first `# Heading` line. */
function takeTitle(markdown) {
	const match = /^#\s+(.+)\n+/m.exec(markdown);
	if (!match) throw new Error('expected a "# Title" heading');
	return { title: match[1].trim(), body: markdown.slice(match.index + match[0].length) };
}

function frontmatter(fields) {
	const lines = Object.entries(fields).map(([key, value]) =>
		typeof value === 'object' ? `${key}:\n${Object.entries(value).map(([k, v]) => `  ${k}: ${JSON.stringify(v)}`).join('\n')}` : `${key}: ${JSON.stringify(value)}`,
	);
	return `---\n${lines.join('\n')}\n---\n\n`;
}

function write(target, text) {
	mkdirSync(dirname(target), { recursive: true });
	writeFileSync(target, text);
}

function read(repoPath) {
	return readFileSync(join(repoDir, repoPath), 'utf8');
}

const notice = (repoPath) =>
	`<!-- Generated from ${repoPath} by website/scripts/sync-content.mjs. Edit that file instead. -->\n\n`;

// Changelog
{
	const { body } = takeTitle(read('CHANGELOG.md'));
	write(
		join(contentDir, 'changelog.md'),
		frontmatter({
			title: 'Changelog',
			description: 'Every MarketForge release: breaking changes, new features and fixes.',
			editUrl: `${REPO_URL}/edit/dev/CHANGELOG.md`,
			tableOfContents: { minHeadingLevel: 2, maxHeadingLevel: 2 },
		}) +
			notice('CHANGELOG.md') +
			`Releases follow [semantic versioning](https://semver.org/). A seed's candles only change in a new **major** version: see the [reproducibility contract](${pageLink('changelog/', 'docs/reference/reproducibility/')}). Packages are on [PyPI](https://pypi.org/project/marketforge/#history) and [GitHub releases](${REPO_URL}/releases).\n\n` +
			rewriteLinks(body, 'CHANGELOG.md'),
	);
}

// Glossary
{
	const { body } = takeTitle(read('GLOSSARY.md'));
	write(
		join(contentDir, 'docs', 'reference', 'glossary.md'),
		frontmatter({
			title: 'Glossary',
			description: 'The vocabulary MarketForge uses in its code, its documentation and its output.',
			editUrl: `${REPO_URL}/edit/dev/GLOSSARY.md`,
		}) +
			notice('GLOSSARY.md') +
			rewriteLinks(body, 'GLOSSARY.md'),
	);
}

// Architecture decision records
{
	const outDir = join(contentDir, 'docs', 'adr');
	rmSync(outDir, { recursive: true, force: true });
	const files = readdirSync(join(repoDir, 'docs', 'adr'))
		.filter((name) => name.endsWith('.md'))
		.sort();
	for (const name of files) {
		const repoPath = `docs/adr/${name}`;
		const { title, body } = takeTitle(read(repoPath));
		const number = name.slice(0, 4);
		write(
			join(outDir, name.toLowerCase()),
			frontmatter({
				title: `ADR ${number}: ${title}`,
				description: title,
				editUrl: `${REPO_URL}/edit/dev/${repoPath}`,
				sidebar: { label: `${number} · ${title}`, order: Number(number) },
			}) +
				notice(repoPath) +
				rewriteLinks(body, repoPath),
		);
	}
	console.log(`synced CHANGELOG.md, GLOSSARY.md and ${files.length} ADRs into ${relative(repoDir, contentDir)}`);
}

// Brand guidelines and their assets
{
	const page = 'docs/brand';
	const { body } = takeTitle(read('docs/brand/README.md'));
	const assetsDir = join(repoDir, 'docs', 'brand', 'assets');
	const publicDir = join(websiteDir, 'public', 'brand');
	rmSync(publicDir, { recursive: true, force: true });
	mkdirSync(publicDir, { recursive: true });
	for (const name of readdirSync(assetsDir)) copyFileSync(join(assetsDir, name), join(publicDir, name));
	// GitHub picks the <picture> source from the OS colour scheme; the site has its own theme
	// switch, so show both lockups and let the theme hide the wrong one.
	const themed = body.replace(
		/<picture>\s*<source[^>]*srcset="([^"]+)"[^>]*>\s*<img[^>]*src="([^"]+)"[^>]*alt="([^"]*)"[^>]*>\s*<\/picture>|<picture>\s*<source[^>]*srcset="([^"]+)"[^>]*>\s*<img[^>]*alt="([^"]*)"[^>]*src="([^"]+)"[^>]*>\s*<\/picture>/,
		(_, s1, i1, a1, s2, a2, i2) =>
			`<img class="mf-on-dark" src="${s1 ?? s2}" alt="${a1 ?? a2}" height="64">\n<img class="mf-on-light" src="${i1 ?? i2}" alt="${a1 ?? a2}" height="64">`,
	);
	// Raw HTML in the guidelines (<picture>, <img>) points at assets/ too.
	const html = themed.replace(/\b(src|srcset)="assets\/([^"]+)"/g, (_, attr, name) => `${attr}="${posix.relative(page, `brand/${name}`)}"`);
	write(
		join(contentDir, 'docs', 'brand.md'),
		frontmatter({
			title: 'Brand',
			description: 'The MarketForge identity: logo, colours, typography and how to use them.',
			editUrl: `${REPO_URL}/edit/dev/docs/brand/README.md`,
		}) +
			notice('docs/brand/README.md') +
			rewriteLinks(html, 'docs/brand/README.md'),
	);
	console.log('synced docs/brand into the site');
}
