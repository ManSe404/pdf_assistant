<!-- Choosing, starting and deleting conversations, plus the active one's components. -->
<script lang="ts">
	import { formatDateTime } from '../../format.ts';
	import type { ChatSession } from '../../state/chat.svelte.ts';
	import ConfirmButton from '../ConfirmButton.svelte';
	import Icon from '../Icon.svelte';

	let { chat }: { chat: ChatSession } = $props();

	let locked = $derived(chat.streaming || chat.busy);
	// An empty conversation is already "new"; do not pile up more of them.
	let activeIsEmpty = $derived(chat.active !== null && chat.active.messages.length === 0);
</script>

<div class="border-b border-gray-200 px-3 py-2">
	<div class="flex items-center gap-2">
		<label for="conversation" class="sr-only">Razgovor</label>
		<select
			id="conversation"
			class="min-w-0 flex-1 truncate rounded-md border border-gray-300 bg-white py-1.5 pr-8 pl-2 text-sm disabled:opacity-60"
			value={chat.activeId ?? ''}
			disabled={locked || chat.conversations.length === 0}
			onchange={(event) => chat.select(event.currentTarget.value)}
		>
			{#if chat.conversations.length === 0}
				<option value="">{chat.loading ? 'Učitavanje…' : 'Još nema razgovora'}</option>
			{/if}
			{#each chat.conversations as conversation (conversation.id)}
				<option value={conversation.id}
					>{conversation.title} · {formatDateTime(conversation.created_at)}</option
				>
			{/each}
		</select>

		<button
			type="button"
			class="inline-flex shrink-0 items-center gap-1 rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm font-medium whitespace-nowrap hover:bg-gray-50 disabled:opacity-50"
			disabled={locked || activeIsEmpty || chat.loading}
			title={activeIsEmpty ? 'Trenutni razgovor je još prazan' : undefined}
			onclick={() => chat.create()}
		>
			<Icon name="plus" class="size-4" />
			Novi razgovor
		</button>

		{#if chat.active}
			{@const active = chat.active}
			<ConfirmButton
				label="Obriši razgovor"
				iconOnly
				disabled={locked}
				onConfirm={() => chat.remove(active.id)}
			/>
		{/if}
	</div>

	{#if chat.active}
		{@const { llm, retriever, memory } = chat.active.components}
		<p
			class="mt-1 truncate text-xs text-gray-500"
			title="Model: {llm.label} · Pretraga: {retriever.label} · Memorija: {memory.label}"
		>
			<span class="sr-only">Komponente razgovora:</span>
			{llm.label} · {retriever.label} · {memory.label}
		</p>
	{/if}
</div>
