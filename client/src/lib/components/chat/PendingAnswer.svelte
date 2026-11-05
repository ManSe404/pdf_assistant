<!-- The answer while it streams, or a failed one with its error underneath. -->
<script lang="ts">
	import { renderAnswer } from '../../markdown/answer.ts';
	import type { PendingAnswer } from '../../state/chat.svelte.ts';

	let { pending, streaming }: { pending: PendingAnswer; streaming: boolean } = $props();

	// Sources arrive only with the final message, so citations stay plain text here.
	let html = $derived(pending.text ? renderAnswer(pending.text) : '');
</script>

<article class="max-w-[95%] self-start" aria-label="Odgovor u toku" aria-busy={streaming}>
	<div
		class={[
			'rounded-lg rounded-tl-sm border bg-white px-3 py-2 shadow-xs',
			pending.error ? 'border-red-200' : 'border-gray-200'
		]}
	>
		{#if html}
			<!-- Sanitized by renderAnswer (marked, then DOMPurify with a tag allowlist). -->
			<!-- eslint-disable-next-line svelte/no-at-html-tags -->
			<div class="answer prose prose-sm max-w-none break-words">{@html html}</div>
		{:else if streaming}
			<span class="inline-flex gap-1 py-1" aria-label="Odgovor stiže">
				<span class="size-1.5 animate-bounce rounded-full bg-gray-400"></span>
				<span class="size-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:150ms]"
				></span>
				<span class="size-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:300ms]"
				></span>
			</span>
		{/if}
		{#if pending.error}
			<p class="mt-2 border-t border-red-100 pt-2 text-sm text-red-700" role="alert">
				{pending.error}
				<span class="text-red-600/80">Odgovor nije sačuvan.</span>
			</p>
		{/if}
	</div>
</article>
