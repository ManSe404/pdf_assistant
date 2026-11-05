<script lang="ts">
	import { tick } from 'svelte';
	import type { ChatSession } from '../../state/chat.svelte.ts';
	import Icon from '../Icon.svelte';

	interface Props {
		chat: ChatSession;
		/** Why questions cannot be asked right now (PDF not ready), if so. */
		blockedReason: string;
	}

	let { chat, blockedReason }: Props = $props();

	const MAX_LENGTH = 4000;

	let textarea = $state<HTMLTextAreaElement>();
	let disabled = $derived(chat.streaming || chat.busy || blockedReason !== '');
	let length = $derived(chat.draft.length);

	// Grow with the text, up to a limit.
	$effect(() => {
		void chat.draft;
		if (!textarea) {
			return;
		}
		textarea.style.height = 'auto';
		textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
	});

	async function submit(event?: SubmitEvent) {
		event?.preventDefault();
		if (disabled) {
			return;
		}
		const hadFocus = document.activeElement === textarea;
		await chat.send(chat.draft);
		// The box is disabled while the answer streams, which drops its focus.
		if (hadFocus) {
			await tick();
			textarea?.focus();
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		// Enter sends, Shift+Enter makes a new line.
		if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
			event.preventDefault();
			void submit();
		}
	}
</script>

<form class="border-t border-gray-200 bg-white p-3" onsubmit={submit}>
	<label for="question" class="sr-only">Pitanje o dokumentu</label>
	<div class="flex items-end gap-2">
		<textarea
			id="question"
			bind:this={textarea}
			bind:value={chat.draft}
			rows="1"
			maxlength={MAX_LENGTH}
			placeholder={chat.streaming ? 'Odgovor stiže…' : 'Postavite pitanje o dokumentu'}
			aria-describedby="question-hint"
			{disabled}
			onkeydown={handleKeydown}
			class="max-h-40 min-h-10 flex-1 resize-none rounded-md border border-gray-300 px-3 py-2 text-sm disabled:bg-gray-50 disabled:text-gray-500"
		></textarea>
		<button
			type="submit"
			class="inline-flex size-10 shrink-0 items-center justify-center rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
			disabled={disabled || !chat.draft.trim()}
			aria-label="Pošalji"
			title="Pošalji (Enter)"
		>
			<Icon name="send" class="size-5" />
		</button>
	</div>
	<p id="question-hint" class="mt-1 flex justify-between gap-2 text-xs text-gray-500">
		<span>{blockedReason || 'Enter šalje, Shift+Enter nov red.'}</span>
		{#if length > MAX_LENGTH - 500}
			<span class={length >= MAX_LENGTH ? 'text-red-700' : ''}>{length} / {MAX_LENGTH}</span>
		{/if}
	</p>
</form>
