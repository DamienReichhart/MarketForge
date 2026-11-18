/**
 * Small charts for the landing page, drawn to SVG at build time from the real
 * MarketForge output in src/samples/: the regime strip, a mini candlestick
 * chart per regime, and the price paths of one instrument under many seeds.
 * Colours are never set here: every mark carries a class the stylesheets map
 * to a brand token.
 */
import type { Candle } from './candle-chart';

export const REGIMES = ['trend_up', 'trend_down', 'range', 'high_volatility', 'crash'] as const;
export type Regime = (typeof REGIMES)[number];

export interface Run {
	regime: string;
	/** Share of the whole sequence, 0 to 1. */
	share: number;
}

/** Contiguous runs of one regime, as shares of the sequence: the shape of the regime path. */
export function regimeRuns(candles: Candle[]): Run[] {
	const runs: Run[] = [];
	let start = 0;
	for (let i = 1; i <= candles.length; i++) {
		if (i === candles.length || candles[i][7] !== candles[start][7]) {
			runs.push({ regime: String(candles[start][7]), share: (i - start) / candles.length });
			start = i;
		}
	}
	return runs;
}

const r = (v: number) => Math.round(v * 10) / 10;

/** A bare candlestick chart: wicks and bodies coloured by direction, no axes. */
export function miniCandles(candles: Candle[], width = 240, height = 160): string {
	const hi = Math.max(...candles.map((c) => c[2]));
	const lo = Math.min(...candles.map((c) => c[3]));
	const pad = (hi - lo) * 0.08 || 1;
	const y = (p: number) => r(height - ((p - lo + pad) / (hi - lo + 2 * pad)) * height);
	const step = width / candles.length;
	const body = Math.max(1, step * 0.62);
	return candles
		.map((c, i) => {
			const x = r(i * step + step / 2);
			const top = Math.min(y(c[1]), y(c[4]));
			const h = Math.max(1, Math.abs(y(c[1]) - y(c[4])));
			return (
				`<g class="${c[4] >= c[1] ? 'up' : 'down'}">` +
				`<line x1="${x}" x2="${x}" y1="${y(c[2])}" y2="${y(c[3])}"></line>` +
				`<rect x="${r(x - body / 2)}" y="${top}" width="${r(body)}" height="${r(h)}"></rect></g>`
			);
		})
		.join('');
}

export interface Fan {
	/** One `d` attribute per path. */
	lines: string[];
	width: number;
	height: number;
	/** y of the starting level (100), for a baseline. */
	base: number;
	/** Gridlines at round levels inside the range: their y and the level. */
	levels: { y: number; level: number }[];
}

/** Price paths rebased to 100, on a log scale so a halving and a doubling look alike. */
export function fan(paths: number[][], width = 720, height = 360): Fan {
	const all = paths.flat();
	const lo = Math.log(Math.min(...all));
	const hi = Math.log(Math.max(...all));
	const y = (v: number) => r(height - ((Math.log(v) - lo) / (hi - lo)) * height);
	const n = paths[0].length - 1;
	const lines = paths.map((p) => p.map((v, i) => `${i ? 'L' : 'M'}${r((i / n) * width)} ${y(v)}`).join(''));
	const levels = [12.5, 25, 50, 100, 200, 400, 800]
		.filter((v) => Math.log(v) > lo && Math.log(v) < hi)
		.map((level) => ({ y: y(level), level }));
	return { lines, width, height, base: y(100), levels };
}
