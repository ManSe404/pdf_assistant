import type { Attachment } from 'svelte/attachments';
import type { Source } from '../../api/types.ts';

/**
 * Handles clicks on the citation buttons inside rendered answer HTML (they are
 * real buttons, so keyboard activation arrives as a click too).
 */
export function citationClicks(
	getSources: () => Source[],
	onPage: (page: number) => void
): Attachment<HTMLElement> {
	return (element) => {
		const handle = (event: MouseEvent) => {
			const button = (event.target as Element | null)?.closest?.('button[data-cite]');
			if (!button || !element.contains(button)) {
				return;
			}
			const n = Number(button.getAttribute('data-cite'));
			const source = getSources().find((s) => s.n === n);
			if (source) {
				onPage(source.page);
			}
		};
		element.addEventListener('click', handle);
		return () => element.removeEventListener('click', handle);
	};
}
