<script lang="ts">
	import { tick } from 'svelte';
	import type { Pdf } from '../../api/types.ts';
	import type { ChatSession } from '../../state/chat.svelte.ts';
	import Alert from '../Alert.svelte';
	import AssistantMessage from './AssistantMessage.svelte';
	import ChatInput from './ChatInput.svelte';
	import ConversationBar from './ConversationBar.svelte';
	import PendingAnswer from './PendingAnswer.svelte';
	import UserMessage from './UserMessage.svelte';

	interface Props {
		chat: ChatSession;
		pdf: Pdf;
		/** Shows a page of the PDF (citations and sources). */
		onPage: (page: number) => void;
	}

	let { chat, pdf, onPage }: Props = $props();

	let list = $state<HTMLDivElement>();
	let messages = $derived(chat.active?.messages ?? []);
	let pending = $derived(chat.pending?.conversationId === chat.activeId ? chat.pending : null);
	let blockedReason = $derived(
		pdf.status === 'processing'
			? 'Dokument se još obrađuje; pitanja možete postavljati kad bude spreman.'
			: pdf.status === 'failed'
				? 'Obrada dokumenta nije uspela, pa pitanja nisu moguća.'
				: ''
	);

	/** Follow new text at the bottom unless the user scrolled up to read. */
	let followBottom = true;

	function handleScroll() {
		if (list) {
			followBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
		}
	}

	$effect(() => {
		void chat.activeId;
		followBottom = true;
	});

	$effect(() => {
		void messages.length;
		void pending?.text;
		void pending?.error;
		if (followBottom) {
			void tick().then(() => list?.scrollTo({ top: list.scrollHeight }));
		}
	});
</script>

<div class="flex h-full min-h-0 flex-col bg-white">
	<ConversationBar {chat} />

	<div bind:this={list} onscroll={handleScroll} class="min-h-0 flex-1 overflow-y-auto px-3 py-4">
		{#if chat.loading}
			<p class="text-center text-sm text-gray-500">Učitavanje razgovora…</p>
		{:else if chat.loadError}
			<Alert>
				{chat.loadError}
				<button type="button" class="ml-2 font-medium underline" onclick={() => chat.load()}
					>Pokušaj ponovo</button
				>
			</Alert>
		{:else if messages.length === 0 && !pending}
			<div class="mx-auto max-w-sm py-8 text-center text-sm text-gray-600">
				<p class="font-medium text-gray-800">Postavite pitanje o dokumentu.</p>
				<p class="mt-1">
					Odgovori navode izvore kao [1]; klik na izvor prikazuje tu stranu u PDF-u.
				</p>
			</div>
		{:else}
			<div class="flex flex-col gap-4">
				{#each messages as message (message.id)}
					{#if message.role === 'user'}
						<UserMessage content={message.content} />
					{:else}
						<AssistantMessage
							{message}
							voting={chat.voting.has(message.id)}
							onVote={(vote) => chat.vote(message, vote)}
							{onPage}
						/>
					{/if}
				{/each}
				{#if pending}
					<PendingAnswer {pending} streaming={chat.streaming} />
				{/if}
			</div>
		{/if}
	</div>

	{#if chat.notice}
		<div class="px-3 pb-2">
			<Alert onDismiss={() => (chat.notice = '')}>{chat.notice}</Alert>
		</div>
	{/if}

	<ChatInput {chat} {blockedReason} />
</div>
