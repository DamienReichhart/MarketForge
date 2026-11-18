/**
 * The landing page's motion, all of it optional: the page reads the same
 * without script, on a phone and under reduced motion.
 *
 * - Market tabs: the hero's crypto, forex and stocks charts, switched by
 *   click or arrow keys (never on a timer).
 * - Counters: the open-minute figures roll once like an odometer when they
 *   come on screen, resting on the real figures before and after.
 * - Liquid type: the closing command ripples under the pointer and settles
 *   back to crisp type within about a second; one SVG filter, only while it
 *   moves.
 */

const still = () =>
	matchMedia('(prefers-reduced-motion: reduce)').matches || matchMedia('(max-width: 40rem)').matches;
const coarse = () => matchMedia('(pointer: coarse)').matches;

export function mountTabs(list: HTMLElement): void {
	const tabs = [...list.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
	const select = (tab: HTMLButtonElement, focus = false) => {
		for (const t of tabs) {
			const on = t === tab;
			t.setAttribute('aria-selected', String(on));
			t.tabIndex = on ? 0 : -1;
			const panel = document.getElementById(t.getAttribute('aria-controls') ?? '');
			if (panel) panel.hidden = !on;
		}
		if (focus) tab.focus();
	};
	for (const tab of tabs) {
		tab.addEventListener('click', () => select(tab));
		tab.addEventListener('keydown', (event) => {
			const i = tabs.indexOf(tab);
			const next =
				event.key === 'ArrowRight' ? tabs[(i + 1) % tabs.length]
				: event.key === 'ArrowLeft' ? tabs[(i - 1 + tabs.length) % tabs.length]
				: event.key === 'Home' ? tabs[0]
				: event.key === 'End' ? tabs[tabs.length - 1]
				: undefined;
			if (next) {
				event.preventDefault();
				select(next, true);
			}
		});
	}
}

export function mountCounters(row: HTMLElement): void {
	if (still() || !('IntersectionObserver' in window)) return;
	const figures = [...row.querySelectorAll<HTMLElement>('[data-roll]')];
	// Each digit becomes a strip 0-9 twice over, resting on its real digit.
	for (const figure of figures) {
		const text = figure.textContent ?? '';
		const digits = [...text].filter((c) => /\d/.test(c)).length;
		let place = 0;
		figure.textContent = '';
		const shown = document.createElement('span');
		shown.className = 'lp-roll';
		shown.setAttribute('aria-hidden', 'true');
		for (const char of text) {
			if (!/\d/.test(char)) {
				shown.append(char);
				continue;
			}
			place += 1;
			// The right-most digit turns most.
			const turns = 1 + Math.round((place / digits) * 2);
			const strip = document.createElement('span');
			strip.className = 'lp-roll-strip';
			const cells = Array.from({ length: turns * 10 + 1 }, (_, k) => String((Number(char) + k) % 10));
			strip.innerHTML = cells.map((d) => `<span>${d}</span>`).join('');
			strip.style.setProperty('--steps', String(turns * 10));
			const cell = document.createElement('span');
			cell.className = 'lp-roll-cell';
			cell.append(strip);
			shown.append(cell);
		}
		figure.append(shown);
	}
	const observer = new IntersectionObserver(
		(entries) => {
			if (!entries.some((e) => e.isIntersecting)) return;
			row.classList.add('lp-rolling');
			observer.disconnect();
		},
		{ threshold: 0.5 },
	);
	observer.observe(row);
}

let filterId = 0;

export function mountLiquid(head: HTMLElement): void {
	if (still() || coarse() || typeof SVGFEDisplacementMapElement === 'undefined') return;
	const ns = 'http://www.w3.org/2000/svg';
	const id = `lp-liquid-${++filterId}`;
	const svg = document.createElementNS(ns, 'svg');
	svg.setAttribute('width', '0');
	svg.setAttribute('height', '0');
	svg.setAttribute('aria-hidden', 'true');
	svg.classList.add('lp-filter');
	svg.innerHTML =
		`<filter id="${id}" x="-5%" y="-20%" width="110%" height="140%" color-interpolation-filters="sRGB">` +
		`<feTurbulence type="fractalNoise" baseFrequency="0.006 0.013" numOctaves="1" seed="7"></feTurbulence>` +
		`<feDisplacementMap in="SourceGraphic" scale="0" xChannelSelector="R" yChannelSelector="G"></feDisplacementMap></filter>`;
	document.body.append(svg);
	const turbulence = svg.querySelector('feTurbulence')!;
	const displacement = svg.querySelector('feDisplacementMap')!;
	let energy = 0;
	let frame = 0;
	let on = false;
	let last: { x: number; y: number } | undefined;
	let px = 0.5;

	const tick = (time: number) => {
		energy *= 0.9;
		const scale = Math.min(40, energy);
		if (scale < 0.6) {
			if (on) head.style.filter = '';
			on = false;
			frame = 0;
			return;
		}
		displacement.setAttribute('scale', scale.toFixed(1));
		const fx = 0.006 + (px - 0.5) * 0.002;
		const fy = 0.013 + Math.sin(time / 700) * 0.003;
		turbulence.setAttribute('baseFrequency', `${fx.toFixed(4)} ${fy.toFixed(4)}`);
		if (!on) head.style.filter = `url(#${id})`;
		on = true;
		frame = requestAnimationFrame(tick);
	};

	head.addEventListener('pointermove', (event) => {
		const box = head.getBoundingClientRect();
		px = (event.clientX - box.left) / box.width;
		if (last) energy = Math.min(60, energy + Math.hypot(event.clientX - last.x, event.clientY - last.y) * 0.6);
		last = { x: event.clientX, y: event.clientY };
		if (!frame) frame = requestAnimationFrame(tick);
	});
	head.addEventListener('pointerleave', () => {
		last = undefined;
	});
}
