// @ts-check
import starlight from '@astrojs/starlight';
import { defineConfig } from 'astro/config';

import servedPackages from './scripts/served-packages.mjs';
import { codeStyle, codeThemes, languageLabels } from './src/lib/code-theme.mjs';

const repo = 'https://github.com/DamienReichhart/marketforge';

// Served from GitHub Pages as a project site. To move to a custom domain,
// set `site` to it, drop `base`, and add public/CNAME.
export default defineConfig({
	site: 'https://damienreichhart.github.io',
	base: '/marketforge',
	trailingSlash: 'always',
	// Pages that moved: their old addresses stay valid for links already out there.
	redirects: {
		'/docs/guides/cli/': '/marketforge/docs/reference/cli/',
		'/docs/guides/python-api/': '/marketforge/docs/reference/python-api/',
		'/docs/guides/output/': '/marketforge/docs/reference/output/',
	},
	integrations: [
		// Fails the build if a package license-policy.json exempts as not served reaches the site.
		servedPackages(),
		starlight({
			title: 'MarketForge',
			description:
				'Open-source synthetic market data for training AI trading models and stress-testing backtesters: 208 instruments on real trading calendars, every candle labelled with its regime, reproducible from a seed.',
			logo: { src: './src/assets/logo.svg', replacesTitle: false },
			favicon: '/favicon.svg',
			head: [
				{ tag: 'link', attrs: { rel: 'apple-touch-icon', href: '/marketforge/apple-touch-icon.png' } },
				{ tag: 'meta', attrs: { name: 'theme-color', content: '#12161b' } },
				{ tag: 'meta', attrs: { property: 'og:image', content: 'https://damienreichhart.github.io/marketforge/og-image.png' } },
				{ tag: 'meta', attrs: { property: 'og:image:width', content: '1200' } },
				{ tag: 'meta', attrs: { property: 'og:image:height', content: '630' } },
				{ tag: 'meta', attrs: { name: 'twitter:card', content: 'summary_large_image' } },
				{ tag: 'meta', attrs: { name: 'twitter:image', content: 'https://damienreichhart.github.io/marketforge/og-image.png' } },
			],
			social: [{ icon: 'github', label: 'GitHub', href: repo }],
			editLink: { baseUrl: `${repo}/edit/dev/website/` },
			lastUpdated: false,
			credits: false,
			customCss: [
				'@fontsource-variable/dm-sans',
				'@fontsource/dm-mono/400.css',
				'@fontsource/dm-mono/500.css',
				'./src/styles/theme.css',
			],
			components: {
				Footer: './src/components/DocsFooter.astro',
			},
			// Code blocks in the brand's ink and amber (src/lib/code-theme.mjs). The build
			// runs with --force: Astro caches rendered Markdown, and a page rendered before
			// a change here would link a code stylesheet that no longer exists.
			expressiveCode: {
				themes: codeThemes,
				useStarlightDarkModeSwitch: true,
				useStarlightUiThemeColors: false,
				plugins: [languageLabels()],
				defaultProps: { wrap: true, preserveIndent: true },
				styleOverrides: codeStyle,
			},
			sidebar: [
				{
					label: 'Start here',
					items: [
						{ label: 'Overview', slug: 'docs' },
						{ label: 'Playground', slug: 'playground', badge: { text: 'No install', variant: 'note' } },
						{ label: 'Installation', slug: 'docs/installation' },
						{ label: 'Quick start', slug: 'docs/quick-start' },
						{ label: 'Core concepts', slug: 'docs/concepts' },
						{ label: 'Migrating to 5.0', slug: 'docs/migrating-to-5', badge: { text: 'New', variant: 'tip' } },
					],
				},
				{
					label: 'Use cases',
					items: [
						{ label: 'Training ML models', slug: 'docs/use-cases/machine-learning' },
						{ label: 'Backtesting', slug: 'docs/use-cases/backtesting' },
						{ label: 'Stress testing', slug: 'docs/use-cases/stress-testing' },
						{ label: 'What it is not', slug: 'docs/limits' },
					],
				},
				{
					label: 'Guides',
					items: [
						{ label: 'Working with the data', slug: 'docs/guides/working-with-data' },
						{ label: 'Custom instruments', slug: 'docs/guides/custom-instruments' },
						{ label: 'Extending and verifying', slug: 'docs/guides/extend' },
						{ label: 'Validation', slug: 'docs/guides/validation' },
						{ label: 'Performance and scale', slug: 'docs/guides/performance' },
					],
				},
				{
					label: 'Reference',
					items: [
						{ label: 'Command line', slug: 'docs/reference/cli' },
						{ label: 'Python API', slug: 'docs/reference/python-api' },
						{ label: 'Output format', slug: 'docs/reference/output' },
						{ label: 'Markets & calendars', slug: 'docs/reference/markets' },
						{ label: 'The model', slug: 'docs/reference/model' },
						{ label: 'Bid-ask spread', slug: 'docs/reference/spread' },
						{ label: 'Reproducibility', slug: 'docs/reference/reproducibility' },
						{ label: 'Glossary', slug: 'docs/reference/glossary' },
					],
				},
				{
					label: 'Help',
					items: [{ label: 'FAQ and troubleshooting', slug: 'docs/faq' }],
				},
				{
					label: 'Project',
					items: [
						{ label: 'Changelog', slug: 'changelog' },
						{ label: 'Migrating to 4.0', slug: 'docs/migrating-to-4' },
						{
							label: 'Design decisions',
							collapsed: true,
							items: [{ autogenerate: { directory: 'docs/adr' } }],
						},
						{ label: 'Brand', slug: 'docs/brand' },
						{ label: 'Licence', slug: 'docs/licence' },
						{ label: 'Contributing', slug: 'docs/contributing' },
						{ label: 'Security', slug: 'docs/security' },
					],
				},
				{
					label: 'Legal',
					collapsed: true,
					items: [
						{ label: 'Legal notice', slug: 'legal/notice' },
						{ label: 'Privacy', slug: 'legal/privacy' },
						{ label: 'Terms of use', slug: 'legal/terms' },
						{ label: 'Cookies', slug: 'legal/cookies' },
					],
				},
			],
		}),
	],
});
