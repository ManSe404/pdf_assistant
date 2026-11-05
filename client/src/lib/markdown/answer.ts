// Assistant answers: Markdown -> HTML with marked, citations [n] -> buttons, then
// DOMPurify. The model output is untrusted (the PDF text can carry HTML or prompt
// injection), so the sanitizer keeps only a short list of tags and attributes.

import DOMPurify from 'dompurify';
import { Marked, type TokenizerAndRendererExtension, type Tokens } from 'marked';
import type { Source } from '../api/types.ts';

const ALLOWED_TAGS = [
	'p',
	'br',
	'strong',
	'em',
	'del',
	'code',
	'pre',
	'blockquote',
	'ul',
	'ol',
	'li',
	'h1',
	'h2',
	'h3',
	'h4',
	'h5',
	'h6',
	'hr',
	'a',
	'table',
	'thead',
	'tbody',
	'tr',
	'th',
	'td',
	'button'
];

const ALLOWED_ATTR = ['href', 'title', 'start', 'align', 'type', 'data-cite', 'aria-label'];

// Links in an answer open in a new tab and pass no referrer.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
	if (node.tagName === 'A' && node.hasAttribute('href')) {
		node.setAttribute('target', '_blank');
		node.setAttribute('rel', 'noopener noreferrer nofollow');
	}
});

export function escapeHtml(text: string): string {
	return text
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('"', '&quot;')
		.replaceAll("'", '&#39;');
}

interface CitationToken extends Tokens.Generic {
	type: 'citation';
	numbers: number[];
}

/**
 * `[3]` or `[1, 2]` becomes one button per source that exists. Numbers without a
 * matching source (or while the answer is still streaming and sources are unknown)
 * stay plain text. `[1](url)` is a Markdown link, not a citation.
 */
function citations(pages: Map<number, number>): TokenizerAndRendererExtension {
	return {
		name: 'citation',
		level: 'inline',
		start: (src) => src.match(/\[\d/)?.index,
		tokenizer(src): CitationToken | undefined {
			const match = /^\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\](?!\()/.exec(src);
			if (!match) {
				return undefined;
			}
			const numbers = match[1].split(',').map((n) => Number(n.trim()));
			return { type: 'citation', raw: match[0], numbers };
		},
		renderer(token) {
			return (token as CitationToken).numbers
				.map((n) => {
					const page = pages.get(n);
					if (page === undefined) {
						return `[${n}]`;
					}
					const label = `Izvor ${n}, strana ${page}`;
					return `<button type="button" data-cite="${n}" title="${label}" aria-label="${label}">[${n}]</button>`;
				})
				.join('');
		}
	};
}

/**
 * Renders an assistant answer to safe HTML. Citation buttons carry `data-cite="n"`;
 * the caller handles their clicks.
 */
export function renderAnswer(markdown: string, sources: Source[] = []): string {
	if (!DOMPurify.isSupported) {
		// No DOM to sanitize with: show the text, never unsanitized HTML.
		return `<p>${escapeHtml(markdown)}</p>`;
	}

	const pages = new Map(sources.map((source) => [source.n, source.page]));
	const marked = new Marked({
		async: false,
		gfm: true,
		breaks: true,
		extensions: [citations(pages)],
		renderer: {
			// No remote images from model output: an image URL can leak data to a
			// third party (a classic prompt-injection exfiltration). Keep the alt text.
			image: ({ text }) => escapeHtml(text)
		}
	});

	const html = marked.parse(markdown, { async: false });
	return DOMPurify.sanitize(html, {
		ALLOWED_TAGS,
		ALLOWED_ATTR,
		ALLOW_DATA_ATTR: false,
		ALLOW_ARIA_ATTR: false
	});
}
