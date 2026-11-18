// @ts-check
/**
 * The docs' code blocks in the Regimes brand: two syntax themes built from
 * docs/brand/tokens.json, and a plugin that labels every block by language.
 *
 * The palette is ink and amber only. Regime colours mean a regime and the
 * green and red mean candle direction (docs/brand/README.md), so neither may
 * colour code: code reads in neutrals, keywords in amber, and literal values
 * (strings, numbers) in the warm second amber.
 */
import { readFileSync } from 'node:fs';

import { ExpressiveCodeTheme } from '@astrojs/starlight/expressive-code';

const tokens = JSON.parse(readFileSync(new URL('../../../docs/brand/tokens.json', import.meta.url), 'utf8'));

/**
 * @param {'dark' | 'light'} mode
 */
function theme(mode) {
	const t = tokens[mode];
	const rule = (/** @type {string[]} */ scope, /** @type {string} */ foreground, fontStyle = '') => ({
		scope,
		settings: { foreground, ...(fontStyle ? { fontStyle } : {}) },
	});
	return new ExpressiveCodeTheme({
		name: `regimes-${mode}`,
		type: mode,
		colors: {
			'editor.background': t.panel,
			'editor.foreground': t.text,
			'editor.selectionBackground': t.accent_low,
		},
		tokenColors: [
			rule(['source', 'text'], t.text),
			rule(['comment', 'punctuation.definition.comment', 'string.quoted.docstring'], t.muted, 'italic'),
			rule(['punctuation', 'keyword.operator', 'meta.brace', 'punctuation.separator', 'punctuation.definition'], t.muted),
			rule(
				[
					'keyword',
					'storage',
					'storage.type',
					'storage.modifier',
					'keyword.control',
					'keyword.operator.word',
					'keyword.operator.logical.python',
					'constant.language',
					'support.type.property-name.table.toml',
					'entity.name.section',
					'meta.tag.table.toml',
				],
				t.accent,
			),
			rule(['string', 'string.quoted', 'string.unquoted', 'constant.numeric', 'constant.other.date', 'constant.other.time'], t.accent_high),
			rule(['punctuation.definition.string'], t.accent_high),
			rule(['entity.name.command', 'support.function.builtin', 'entity.name.function', 'support.function', 'meta.function-call.generic'], t.text, 'bold'),
			rule(['constant.other.option', 'variable.parameter', 'variable.parameter.function-call', 'meta.parameter'], t.muted),
			rule(['variable', 'entity.name', 'support.type', 'entity.name.type', 'entity.name.class', 'support.type.property-name', 'support.variable'], t.text),
			rule(['punctuation.definition.string.begin.shell', 'punctuation.definition.string.end.shell'], t.accent_high),
		],
	});
}

export const codeThemes = [theme('dark'), theme('light')];

const LABELS = {
	bash: 'Shell',
	sh: 'Shell',
	shell: 'Shell',
	console: 'Shell',
	python: 'Python',
	py: 'Python',
	toml: 'TOML',
	json: 'JSON',
	csv: 'CSV',
	yaml: 'YAML',
	js: 'JavaScript',
	ts: 'TypeScript',
};

/**
 * Gives every block without a title its language as one, so each block has
 * a header that says what it holds. Runs after the frames plugin has taken a
 * file name from the code, so a named file keeps its name.
 *
 * @returns {import('@astrojs/starlight/expressive-code').ExpressiveCodePlugin}
 */
export function languageLabels() {
	return {
		name: 'MarketForge language labels',
		hooks: {
			preprocessCode: ({ codeBlock }) => {
				const props = /** @type {{ title?: string }} */ (codeBlock.props);
				if (props.title) return;
				const label = LABELS[/** @type {keyof typeof LABELS} */ (codeBlock.language)];
				if (label) props.title = label;
			},
		},
	};
}

/** The frame chrome, in the site's tokens so it follows the theme switch. */
export const codeStyle = {
	borderRadius: '8px',
	borderColor: 'var(--mf-line-strong)',
	codeBackground: 'var(--mf-panel)',
	codeFontFamily: 'var(--sl-font-mono)',
	codeFontSize: '0.875rem',
	codeLineHeight: '1.75',
	codePaddingBlock: '1rem',
	codePaddingInline: '1.25rem',
	uiFontFamily: 'var(--sl-font)',
	uiFontSize: '0.8125rem',
	uiPaddingBlock: '0.5rem',
	uiPaddingInline: '1.25rem',
	scrollbarThumbColor: 'var(--mf-line-strong)',
	scrollbarThumbHoverColor: 'var(--mf-muted)',
	focusBorder: 'var(--sl-color-accent-high)',
	frames: {
		shadowColor: 'transparent',
		frameBoxShadowCssValue: 'none',
		editorBackground: 'var(--mf-panel)',
		terminalBackground: 'var(--mf-panel)',
		editorTabBarBackground: 'var(--mf-raised)',
		editorTabBarBorderColor: 'var(--mf-line)',
		editorTabBarBorderBottomColor: 'var(--mf-line)',
		editorActiveTabBackground: 'transparent',
		editorActiveTabForeground: 'var(--mf-muted)',
		editorActiveTabBorderColor: 'transparent',
		editorActiveTabIndicatorHeight: '0',
		editorActiveTabIndicatorTopColor: 'transparent',
		editorActiveTabIndicatorBottomColor: 'transparent',
		editorTabsMarginInlineStart: '0',
		editorTabsMarginBlockStart: '0',
		editorTabBorderRadius: '0',
		terminalTitlebarBackground: 'var(--mf-raised)',
		terminalTitlebarForeground: 'var(--mf-muted)',
		terminalTitlebarBorderBottomColor: 'var(--mf-line)',
		terminalTitlebarDotsOpacity: '0',
		inlineButtonBackground: 'var(--mf-raised)',
		inlineButtonForeground: 'var(--mf-muted)',
		inlineButtonBorder: 'var(--mf-line-strong)',
		inlineButtonBorderOpacity: '1',
		inlineButtonBackgroundIdleOpacity: '1',
		inlineButtonBackgroundHoverOrFocusOpacity: '1',
		inlineButtonBackgroundActiveOpacity: '1',
		tooltipSuccessBackground: 'var(--sl-color-accent)',
		tooltipSuccessForeground: 'var(--mf-bg)',
	},
	textMarkers: {
		markBackground: 'var(--sl-color-accent-low)',
		markBorderColor: 'var(--sl-color-accent)',
	},
};
