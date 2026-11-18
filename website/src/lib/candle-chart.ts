/**
 * The candlestick chart of the site, shared by the landing page (rendered at
 * build time) and the playground (rendered in the browser from data generated
 * there): candles, volume, the hidden regime of every candle as shaded bands,
 * and a readout of the candle under the pointer. Styles are global, in
 * src/styles/candle-chart.css, so markup created at runtime is styled too.
 */

/** [time (s), open, high, low, close, volume, spread, regime]. */
export type Candle = [number, number, number, number, number, number, number | null, string | null];

export interface ChartOptions {
	instrument: string;
	/** Shown after the symbol, e.g. "H1 · crypto · seed 4". */
	meta: string;
	/** Accessible description of the plot. */
	label: string;
	/** A command shown in the footer, prefixed with `$`. */
	command?: string;
}

export const REGIME_LABELS: Record<string, string> = {
	trend_up: 'Trend up',
	trend_down: 'Trend down',
	range: 'Range',
	high_volatility: 'High volatility',
	crash: 'Crash',
};

const W = 1200;
const H = 440;
const priceTop = 16;
const priceBottom = 340;
const volTop = 362;
const volBottom = 432;
const DAY = 86_400;
const MAX_TICKS = 12;

const escape = (s: string) =>
	s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

/** Decimals that show a price's moves: 2 for stocks and crypto, 3 to 6 for forex. */
export function priceDecimals(price: number): number {
	if (!(price > 0)) return 2;
	return Math.min(6, Math.max(2, 5 - Math.floor(Math.log10(price))));
}

const formatter = (decimals: number) => (n: number) =>
	n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

const monthDay = (t: number) =>
	new Date(t * 1000).toLocaleDateString('en-US', { month: 'short', day: '2-digit', timeZone: 'UTC' });
const monthYear = (t: number) =>
	new Date(t * 1000).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
const hourMinute = (t: number) => new Date(t * 1000).toISOString().slice(11, 16);
const month = (t: number) => {
	const d = new Date(t * 1000);
	return d.getUTCFullYear() * 12 + d.getUTCMonth();
};

// Tick intervals, finest first: the finest one that gives at most MAX_TICKS
// labels is used, and a label goes on the first candle of each interval
// (on the very first candle only if it starts one).
const INTERVALS: { key: (t: number) => number; label: (t: number) => string }[] = [
	...[1, 2, 3, 6, 12].map((h) => ({ key: (t: number) => Math.floor(t / (h * 3600)), label: hourMinute })),
	{ key: (t) => Math.floor(t / DAY), label: monthDay },
	{ key: (t) => Math.floor((t / DAY + 3) / 7), label: monthDay }, // weeks start on Monday
	{ key: month, label: monthYear },
	{ key: (t) => Math.floor(month(t) / 3), label: monthYear },
	{ key: (t) => new Date(t * 1000).getUTCFullYear(), label: monthYear },
];

function timeTicks(candles: Candle[]): { index: number; label: string }[] {
	for (const { key, label } of INTERVALS) {
		const ticks = candles
			.map((c, i) => ({ i, t: c[0] }))
			.filter(({ i, t }) => key(t) !== key(i > 0 ? candles[i - 1][0] : t - 1))
			.map(({ i, t }) => ({ index: i, label: label(t) }));
		if (ticks.length <= MAX_TICKS) return ticks;
	}
	return [];
}

/** The chart's HTML: a `<figure class="mf-chart">` to insert as-is. */
export function chartMarkup(candles: Candle[], options: ChartOptions): string {
	if (candles.length === 0) return '';
	const lows = candles.map((c) => c[3]);
	const highs = candles.map((c) => c[2]);
	const pad = (Math.max(...highs) - Math.min(...lows)) * 0.04 || Math.abs(highs[0]) * 0.01 || 1;
	const min = Math.min(...lows) - pad;
	const max = Math.max(...highs) + pad;
	const maxVol = Math.max(...candles.map((c) => c[5])) || 1;
	const step = W / candles.length;
	const body = Math.max(1, step * 0.62);
	const y = (price: number) => priceTop + ((max - price) / (max - min)) * (priceBottom - priceTop);
	const x = (i: number) => i * step + step / 2;
	const last = candles.at(-1)!;
	const decimals = priceDecimals(last[4]);
	const fmt = formatter(decimals);
	const hasSpread = last[6] !== null;
	const hasRegime = last[7] !== null;

	// Regime runs, for the shaded bands.
	const runs: { regime: string; from: number; to: number }[] = [];
	if (hasRegime)
		candles.forEach((c, i) => {
			const run = runs.at(-1);
			if (run && run.regime === c[7]) run.to = i;
			else runs.push({ regime: c[7] ?? '', from: i, to: i });
		});

	// Price gridlines at round numbers.
	const rawStep = (max - min) / 5;
	const magnitude = 10 ** Math.floor(Math.log10(rawStep));
	const gridStep = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rawStep) ?? rawStep;
	const gridPrices: number[] = [];
	for (let p = Math.ceil(min / gridStep) * gridStep; p <= max; p += gridStep) gridPrices.push(p);
	const gridFmt = formatter(Math.max(0, -Math.floor(Math.log10(gridStep)) + (gridStep / magnitude === 2.5 ? 1 : 0)));

	const ticks = timeTicks(candles);
	const cell = (k: number, name: string, value: string, extra = '') =>
		`<div${extra}><dt>${name}</dt><dd data-k="${k}"${k === 7 ? ` class="mf-regime-tag r-${escape(String(last[7]))}"` : ''}>${value}</dd></div>`;

	const bands = runs
		.map((r) => `<rect class="band r-${escape(r.regime)}" x="${r.from * step}" y="0" width="${(r.to - r.from + 1) * step}" height="${H}"></rect>`)
		.join('');
	const grid = gridPrices.map((p) => `<line class="grid" x1="0" x2="${W}" y1="${y(p)}" y2="${y(p)}"></line>`).join('');
	const bars = candles
		.map((c, i) => {
			const top = y(Math.max(c[1], c[4]));
			const h = Math.max(1, Math.abs(y(c[1]) - y(c[4])));
			const vh = (c[5] / maxVol) * (volBottom - volTop);
			return (
				`<g class="${c[4] >= c[1] ? 'up' : 'down'}">` +
				`<line class="wick" x1="${x(i)}" x2="${x(i)}" y1="${y(c[2])}" y2="${y(c[3])}"></line>` +
				`<rect class="body" x="${x(i) - body / 2}" y="${top}" width="${body}" height="${h}"></rect>` +
				`<rect class="vol" x="${x(i) - body / 2}" y="${volBottom - vh}" width="${body}" height="${vh}"></rect></g>`
			);
		})
		.join('');
	const legend = hasRegime
		? `<ul class="mf-legend" aria-label="Regimes">${Object.entries(REGIME_LABELS)
				.map(([key, label]) => `<li><i class="r-${key}"></i>${label}</li>`)
				.join('')}</ul>`
		: '<span></span>';

	return (
		`<figure class="mf-chart" data-candles="${escape(JSON.stringify(candles))}" data-decimals="${decimals}">` +
		`<figcaption class="mf-chart-bar"><div class="mf-chart-id">` +
		`<span class="mf-chart-symbol">${escape(options.instrument)}</span>` +
		`<span class="mf-chart-meta">${escape(options.meta)}</span></div>` +
		`<dl class="mf-chart-readout" aria-live="polite">` +
		cell(1, 'O', fmt(last[1])) +
		cell(2, 'H', fmt(last[2])) +
		cell(3, 'L', fmt(last[3])) +
		cell(4, 'C', fmt(last[4])) +
		(hasSpread ? cell(6, 'Spread', (last[6] as number).toFixed(Math.max(4, decimals)), ' class="mf-hide-sm"') : '') +
		(hasRegime ? cell(7, 'Regime', REGIME_LABELS[last[7] as string] ?? String(last[7])) : '') +
		`</dl></figcaption>` +
		`<div class="mf-chart-plot">` +
		`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${escape(options.label)}">` +
		bands +
		grid +
		`<line class="grid" x1="0" x2="${W}" y1="${volTop - 10}" y2="${volTop - 10}"></line>` +
		bars +
		`<line class="cursor" x1="0" x2="0" y1="0" y2="${H}"></line></svg>` +
		`<div class="mf-axis-y" aria-hidden="true">${gridPrices
			.map((p) => `<span style="top:${(y(p) / H) * 100}%">${gridFmt(p)}</span>`)
			.join('')}</div>` +
		`<div class="mf-axis-x" aria-hidden="true">${ticks
			.map((t, n) => `<span${n % 2 ? ' class="mf-hide-sm"' : ''} style="left:${(x(t.index) / W) * 100}%">${t.label}</span>`)
			.join('')}</div></div>` +
		`<div class="mf-chart-foot">${legend}` +
		(options.command ? `<code class="mf-chart-cmd">$ ${escape(options.command)}</code>` : '') +
		`</div></figure>`
	);
}

/** Make the readout follow the pointer over a chart made by {@link chartMarkup}. */
export function attachReadout(figure: HTMLElement): void {
	const candles = JSON.parse(figure.dataset.candles ?? '[]') as Candle[];
	if (candles.length === 0) return;
	const decimals = Number(figure.dataset.decimals ?? 2);
	const fmt = formatter(decimals);
	const svg = figure.querySelector('svg')!;
	const cursor = figure.querySelector<SVGLineElement>('.cursor')!;
	const cells = figure.querySelectorAll<HTMLElement>('[data-k]');
	const show = (i: number) => {
		const c = candles[i];
		for (const cell of cells) {
			const k = Number(cell.dataset.k);
			if (k === 7) {
				cell.textContent = REGIME_LABELS[c[7] as string] ?? String(c[7]);
				cell.className = `mf-regime-tag r-${c[7]}`;
			} else cell.textContent = k === 6 ? (c[6] as number).toFixed(Math.max(4, decimals)) : fmt(c[k] as number);
		}
	};
	svg.addEventListener('pointermove', (event: PointerEvent) => {
		const box = svg.getBoundingClientRect();
		const ratio = Math.min(0.9999, Math.max(0, (event.clientX - box.left) / box.width));
		const i = Math.floor(ratio * candles.length);
		const cx = ((i + 0.5) / candles.length) * W;
		cursor.setAttribute('x1', String(cx));
		cursor.setAttribute('x2', String(cx));
		cursor.classList.add('on');
		show(i);
	});
	svg.addEventListener('pointerleave', () => {
		cursor.classList.remove('on');
		show(candles.length - 1);
	});
}
