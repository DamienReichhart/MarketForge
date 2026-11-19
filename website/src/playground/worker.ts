/// <reference lib="webworker" />
/**
 * The playground's Web Worker: runs MarketForge in Pyodide off the page's
 * main thread, so a simulation never freezes the page and can be cancelled
 * by terminating the worker. Everything it loads is served by the site itself
 * (public/playground/, filled by scripts/sync-playground.mjs).
 *
 * Messages in:  { id, type: 'check' | 'run' | 'candles' | 'export', ...args }
 * Messages out: { type: 'status', text } while loading,
 *               { id, ok: true, value } or { id, ok: false, error } per message.
 */
import limits from './limits.json';

interface PyProxy {
	toJs(): Uint8Array;
	destroy(): void;
}
interface Runner {
	describe(): string;
	check(request: string, limits: string): string;
	run(request: string, limits: string): string;
	candles(symbol: string, timeframe: string, limit: number): string;
	export(timeframe: string, fmt: string): PyProxy;
}
interface Pyodide {
	loadPackage(names: string | string[], options?: { messageCallback?: (message: string) => void }): Promise<unknown>;
	pyimport(name: string): Runner;
	FS: { writeFile(path: string, data: string | Uint8Array): void };
}
interface Manifest {
	marketforge: string;
	wheel: string;
	pyodide: string;
	packages: string[];
	downloadMB: number;
}

const scope = self as unknown as DedicatedWorkerGlobalScope;
const root = new URL(`${import.meta.env.BASE_URL.replace(/\/?$/, '/')}playground/`, scope.location.origin).href;
const limitsJson = JSON.stringify(limits);
const status = (text: string) => scope.postMessage({ type: 'status', text });

let runner: Promise<Runner> | undefined;

async function boot(): Promise<Runner> {
	const manifest = (await (await fetch(`${root}manifest.json`)).json()) as Manifest;
	status(`Downloading Python and MarketForge ${manifest.marketforge} (${manifest.downloadMB} MB, once)…`);
	const { loadPyodide } = (await import(/* @vite-ignore */ `${root}pyodide/pyodide.mjs`)) as {
		loadPyodide(options: { indexURL: string }): Promise<Pyodide>;
	};
	const py = await loadPyodide({ indexURL: `${root}pyodide/` });
	const quiet = { messageCallback: () => {} };
	await py.loadPackage(manifest.packages, quiet);
	await py.loadPackage(`${root}${manifest.wheel}`, quiet);
	const source = new Uint8Array(await (await fetch(`${root}runner.py`)).arrayBuffer());
	py.FS.writeFile('/home/pyodide/playground_runner.py', source);
	status('Starting MarketForge…');
	const module = py.pyimport('playground_runner');
	module.describe();
	return module;
}

/** The last line of a Python traceback, without the exception's type for our own messages. */
function reason(error: unknown): string {
	const text = String(error instanceof Error ? error.message : error).trim();
	const last = text.split('\n').at(-1) ?? text;
	return last.replace(/^ValueError: /, '');
}

scope.onmessage = async (event: MessageEvent) => {
	const { id, type, ...args } = event.data as { id: number; type: string; [key: string]: unknown };
	try {
		// A failed start (a lost connection) is retried by the next message.
		runner ??= boot().catch((error: unknown) => {
			runner = undefined;
			throw error;
		});
		const py = await runner;
		if (type === 'run') status('Simulating…');
		let value: unknown;
		if (type === 'check') value = JSON.parse(py.check(JSON.stringify(args.request), limitsJson));
		else if (type === 'run') value = JSON.parse(py.run(JSON.stringify(args.request), limitsJson));
		else if (type === 'candles')
			value = JSON.parse(py.candles(String(args.symbol), String(args.timeframe), limits.chartCandles));
		else if (type === 'export') {
			const proxy = py.export(String(args.timeframe), String(args.fmt));
			const bytes = proxy.toJs();
			proxy.destroy();
			scope.postMessage({ id, ok: true, value: bytes }, [bytes.buffer]);
			return;
		} else throw new Error(`unknown message ${type}`);
		scope.postMessage({ id, ok: true, value });
	} catch (error) {
		scope.postMessage({ id, ok: false, error: reason(error) });
	}
};
