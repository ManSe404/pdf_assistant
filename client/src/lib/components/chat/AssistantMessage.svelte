<script lang="ts">
	import type { Message, Vote } from '../../api/types.ts';
	import { renderAnswer } from '../../markdown/answer.ts';
	import Icon from '../Icon.svelte';
	import Sources from './Sources.svelte';
	import { citationClicks } from './citations.ts';

	interface Props {
		message: Message;
		voting: boolean;
		onVote: (vote: Vote) => void;
		onPage: (page: number) => void;
	}

	let { message, voting, onVote, onPage }: Props = $props();

	let html = $derived(renderAnswer(message.content, message.sources));

	const voteStyle =
		'rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-50 aria-pressed:text-blue-700';
</script>

<article class="max-w-[95%] self-start" aria-label="Odgovor">
	<div class="rounded-lg rounded-tl-sm border border-gray-200 bg-white px-3 py-2 shadow-xs">
		<div
			class="answer prose prose-sm max-w-none break-words"
			{@attach citationClicks(() => message.sources, onPage)}
		>
			<!-- Sanitized by renderAnswer (marked, then DOMPurify with a tag allowlist). -->
			<!-- eslint-disable-next-line svelte/no-at-html-tags -->
			{@html html}
		</div>
		<Sources sources={message.sources} {onPage} />
	</div>
	<div class="mt-1 flex items-center gap-1">
		<button
			type="button"
			class={voteStyle}
			aria-pressed={message.vote === 1}
			aria-label="Dobar odgovor"
			title={message.vote === 1 ? 'Ukloni glas' : 'Dobar odgovor'}
			disabled={voting}
			onclick={() => onVote(1)}
		>
			<Icon name={message.vote === 1 ? 'thumb-up-solid' : 'thumb-up'} class="size-4" />
		</button>
		<button
			type="button"
			class={voteStyle}
			aria-pressed={message.vote === -1}
			aria-label="Loš odgovor"
			title={message.vote === -1 ? 'Ukloni glas' : 'Loš odgovor'}
			disabled={voting}
			onclick={() => onVote(-1)}
		>
			<Icon name={message.vote === -1 ? 'thumb-down-solid' : 'thumb-down'} class="size-4" />
		</button>
	</div>
</article>
