<!-- Compact source list under an answer: page chips, passage text on demand. -->
<script lang="ts">
	import type { Source } from '../../api/types.ts';

	interface Props {
		sources: Source[];
		onPage: (page: number) => void;
	}

	let { sources, onPage }: Props = $props();

	let open = $state(false);
	const listId = $props.id();

	let sorted = $derived([...sources].sort((a, b) => a.n - b.n));
</script>

{#if sorted.length}
	<div class="mt-2 text-xs">
		<div class="flex flex-wrap items-center gap-1">
			<span class="text-gray-500">Izvori:</span>
			{#each sorted as source (source.n)}
				<button
					type="button"
					class="rounded bg-gray-100 px-1.5 py-0.5 text-gray-700 hover:bg-blue-50 hover:text-blue-700"
					title="Prikaži stranu {source.page}"
					onclick={() => onPage(source.page)}
				>
					[{source.n}] str. {source.page}
				</button>
			{/each}
			<button
				type="button"
				class="px-1 text-blue-700 hover:underline"
				aria-expanded={open}
				aria-controls={listId}
				onclick={() => (open = !open)}
			>
				{open ? 'Sakrij odlomke' : 'Prikaži odlomke'}
			</button>
		</div>
		{#if open}
			<ol id={listId} class="mt-2 grid gap-2">
				{#each sorted as source (source.n)}
					<li class="rounded-md border border-gray-200 bg-gray-50 p-2">
						<button
							type="button"
							class="font-medium text-gray-800 hover:text-blue-700 hover:underline"
							onclick={() => onPage(source.page)}>[{source.n}] strana {source.page}</button
						>
						<p class="mt-1 line-clamp-6 whitespace-pre-line text-gray-700">{source.text}</p>
					</li>
				{/each}
			</ol>
		{/if}
	</div>
{/if}
