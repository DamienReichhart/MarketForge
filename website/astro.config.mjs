// @ts-check
import starlight from '@astrojs/starlight';
import { defineConfig } from 'astro/config';

const repo = 'https://github.com/DamienReichhart/MarketForge';

// Served from GitHub Pages as a project site. To move to a custom domain,
// set `site` to it, drop `base`, and add public/CNAME.
export default defineConfig({
	site: 'https://damienreichhart.github.io',
	base: '/MarketForge',
	trailingSlash: 'always',
	integrations: [
		starlight({
			title: 'MarketForge',
			description:
				'Open-source synthetic market data for training AI trading models and stress-testing backtesters: labelled regimes, real trading calendars, bit-for-bit reproducible.',
			logo: { src: './src/assets/logo.svg', replacesTitle: false },
			favicon: '/favicon.svg',
			head: [
				{ tag: 'link', attrs: { rel: 'apple-touch-icon', href: '/MarketForge/apple-touch-icon.png' } },
				{ tag: 'meta', attrs: { name: 'theme-color', content: '#12161b' } },
				{ tag: 'meta', attrs: { property: 'og:image', content: 'https://damienreichhart.github.io/MarketForge/og-image.png' } },
				{ tag: 'meta', attrs: { property: 'og:image:width', content: '1200' } },
				{ tag: 'meta', attrs: { property: 'og:image:height', content: '630' } },
				{ tag: 'meta', attrs: { name: 'twitter:card', content: 'summary_large_image' } },
				{ tag: 'meta', attrs: { name: 'twitter:image', content: 'https://damienreichhart.github.io/MarketForge/og-image.png' } },
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
			expressiveCode: {
				themes: ['github-dark-default', 'github-light-default'],
				styleOverrides: {
					borderRadius: '4px',
					borderColor: 'var(--mf-line)',
					codeFontFamily: 'var(--sl-font-mono)',
					uiFontFamily: 'var(--sl-font)',
					frames: { shadowColor: 'transparent' },
				},
			},
			sidebar: [
				{
					label: 'Start here',
					items: [
						{ label: 'Overview', slug: 'docs' },
						{ label: 'Installation', slug: 'docs/installation' },
						{ label: 'Quick start', slug: 'docs/quick-start' },
						{ label: 'What it is not', slug: 'docs/limits' },
					],
				},
				{
					label: 'Use cases',
					items: [
						{ label: 'Training ML models', slug: 'docs/use-cases/machine-learning' },
						{ label: 'Backtesting', slug: 'docs/use-cases/backtesting' },
						{ label: 'Stress testing', slug: 'docs/use-cases/stress-testing' },
					],
				},
				{
					label: 'Guides',
					items: [
						{ label: 'Command line', slug: 'docs/guides/cli' },
						{ label: 'Python API', slug: 'docs/guides/python-api' },
						{ label: 'Output format', slug: 'docs/guides/output' },
						{ label: 'Extending a dataset', slug: 'docs/guides/extend' },
						{ label: 'Custom instruments', slug: 'docs/guides/custom-instruments' },
						{ label: 'Validation', slug: 'docs/guides/validation' },
					],
				},
				{
					label: 'Reference',
					items: [
						{ label: 'Markets & calendars', slug: 'docs/reference/markets' },
						{ label: 'The model', slug: 'docs/reference/model' },
						{ label: 'Bid-ask spread', slug: 'docs/reference/spread' },
						{ label: 'Reproducibility', slug: 'docs/reference/reproducibility' },
						{ label: 'Glossary', slug: 'docs/reference/glossary' },
					],
				},
				{
					label: 'Project',
					items: [
						{ label: 'Changelog', slug: 'changelog' },
						{
							label: 'Design decisions',
							collapsed: true,
							items: [{ autogenerate: { directory: 'docs/adr' } }],
						},
						{ label: 'Brand', slug: 'docs/brand' },
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
