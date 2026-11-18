// Runs the built playground's Python side under Node, as the page's worker
// does in the browser: the self-hosted Pyodide, its wheels and the
// MarketForge wheel from dist/playground/, then runner.py. CI runs it after
// `npm run build`, so a Pyodide, pandas or MarketForge change that breaks the
// playground fails CI instead of the page.

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const websiteDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const playground = join(websiteDir, 'dist', 'playground');
const limits = readFileSync(join(websiteDir, 'src', 'playground', 'limits.json'), 'utf8');
const manifest = JSON.parse(readFileSync(join(playground, 'manifest.json'), 'utf8'));

let failures = 0;
const check = (ok, what) => {
	console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`);
	if (!ok) failures += 1;
};

const { loadPyodide } = await import(pathToFileURL(join(playground, 'pyodide', 'pyodide.mjs')).href);
const started = performance.now();
const py = await loadPyodide({ indexURL: `${join(playground, 'pyodide')}/`, packageCacheDir: join(playground, 'pyodide') });
// Only the site's own files: a package missing from dist/ must fail here, not
// be fetched from Pyodide's CDN.
await py.loadPackage(manifest.packages, { messageCallback: () => {} });
await py.loadPackage(join(playground, manifest.wheel), { messageCallback: () => {} });
py.FS.writeFile('/home/pyodide/playground_runner.py', readFileSync(join(playground, 'runner.py')));
const runner = py.pyimport('playground_runner');
console.log(`loaded in ${((performance.now() - started) / 1000).toFixed(1)} s`);

const described = JSON.parse(runner.describe());
check(described.version === manifest.marketforge, `MarketForge ${described.version} is the version the site was built with`);
check(py.runPython('import sys; "numba" not in sys.modules'), 'runs without Numba');

const request = {
	market: 'crypto',
	instruments: ['BTCUSD'],
	start: '2024-03-01',
	days: 2,
	seed: 4,
	timeframes: ['m1', 'H1'],
	include_regime: true,
	include_spread: true,
	anomalies: [],
	include_bid_ask: false,
};
const before = JSON.parse(runner.check(JSON.stringify(request), limits));
check(before.ok && before.calibration_seconds > 0, `the first crypto request counts the regime calibration (${before.calibration_seconds} s)`);
const summary = JSON.parse(runner.run(JSON.stringify(request), limits));
const after = JSON.parse(runner.check(JSON.stringify(request), limits));
check(after.calibration_seconds === 0, 'the next one does not');
check(summary.rows === 2 * 1440 + 2 * 24, `generates ${summary.rows} candles (2 days of m1 and H1)`);

const chart = JSON.parse(runner.candles('BTCUSD', 'H1', 500));
const candle = chart.candles[0];
check(chart.total === 48 && chart.candles.length === 48, 'returns the chart candles');
check(
	candle.length === 8 && typeof candle[6] === 'number' && typeof candle[7] === 'string',
	`a chart candle is [time, o, h, l, c, v, spread, regime]: ${JSON.stringify(candle)}`,
);

const csvProxy = runner.export('H1', 'csv');
const csv = new TextDecoder().decode(csvProxy.toJs());
csvProxy.destroy();
const lines = csv.trim().split('\n');
check(lines[0] === 'symbol,time,open,high,low,close,volume,spread,regime', `CSV header: ${lines[0]}`);
check(lines.length === 49 && lines[1].startsWith('BTCUSD,2024-03-01T00:00:00Z,'), 'CSV rows');

const parquetProxy = runner.export('m1', 'parquet');
const parquet = parquetProxy.toJs();
parquetProxy.destroy();
check(new TextDecoder().decode(parquet.slice(0, 4)) === 'PAR1', `Parquet file (${parquet.length} bytes)`);

const tooBig = JSON.parse(runner.check(JSON.stringify({ ...request, instruments: [], days: 365 }), limits));
check(!tooBig.ok && tooBig.reason.startsWith('Too large for the web version'), `refuses a year of crypto m1: ${tooBig.reason}`);
let refused = false;
try {
	runner.run(JSON.stringify({ ...request, instruments: [], days: 365 }), limits);
} catch (error) {
	refused = String(error).includes('Too large for the web version');
}
check(refused, 'run() refuses it too');

if (failures) {
	console.error(`${failures} playground check(s) failed`);
	process.exit(1);
}
console.log('the playground works');
