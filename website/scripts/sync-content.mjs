// Copies the repository's own Markdown into the docs site, so the changelog,
// the glossary and the architecture decision records have a single source of
// truth: the files at the repository root. Runs before every dev and build.
//
//   CHANGELOG.md   -> src/content/docs/changelog.md
//   GLOSSARY.md    -> src/content/docs/docs/reference/glossary.md
//   docs/adr/*.md  -> src/content/docs/docs/adr/*.md
//
// Relative links are rewritten: links to synced files point to their page on
// the site, any other repository path points to the file on GitHub.

import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, posix, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const websiteDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const repoDir = join(websiteDir, '..');
const contentDir = join(websiteDir, 'src', 'content', 'docs');

const BASE = '/MarketForge';
const REPO_URL = 'https://github.com/DamienReichhart/MarketForge';
const BRANCH = 'main';

/** Site URL of a repository path that is published on the site, or undefined. */
function sitePath(repoPath) {
	if (repoPath === 'CHANGELOG.md') return `${BASE}/changelog/`;
	if (repoPath === 'GLOSSARY.md') return `${BASE}/docs/reference/glossary/`;
	const adr = /^docs\/adr\/([^/]+)\.md$/.exec(repoPath);
	if (adr) return `${BASE}/docs/adr/${adr[1].toLowerCase()}/`;
	return undefined;
}

/** Rewrites the relative Markdown links of a file found at `sourcePath` (repository-relative). */
function rewriteLinks(markdown, sourcePath) {
	const sourceDir = posix.dirname(sourcePath);
	return markdown.replace(/\]\(([^)\s]+)\)/g, (match, target) => {
		if (/^([a-z]+:|#|\/)/i.test(target)) return match;
		const [path, anchor] = target.split('#');
		const resolved = posix.normalize(posix.join(sourceDir, path)).replace(/\/$/, '');
		const hash = anchor ? `#${anchor}` : '';
		const page = sitePath(resolved);
		if (page) return `](${page}${hash})`;
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
			`Releases follow [semantic versioning](https://semver.org/). A seed's candles only change in a new **major** version: see the [reproducibility contract](${BASE}/docs/reference/reproducibility/). Packages are on [PyPI](https://pypi.org/project/marketforge/#history) and [GitHub releases](${REPO_URL}/releases).\n\n` +
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
