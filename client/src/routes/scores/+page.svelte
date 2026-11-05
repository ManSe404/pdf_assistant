<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api/client.ts';
	import { messageOf } from '#lib/api/errors.ts';
	import type { ComponentType, Scores } from '#lib/api/types.ts';
	import Alert from '#lib/components/Alert.svelte';
	import ScoreChart from '#lib/components/ScoreChart.svelte';

	const SECTIONS: { type: ComponentType; title: string }[] = [
		{ type: 'llm', title: 'Jezički model' },
		{ type: 'retriever', title: 'Pretraga (broj isečaka)' },
		{ type: 'memory', title: 'Memorija (istorija razgovora)' }
	];

	let scores = $state<Scores | null>(null);
	let error = $state('');

	async function load() {
		error = '';
		try {
			scores = await api.get<Scores>('/scores');
		} catch (caught) {
			error = messageOf(caught);
		}
	}

	onMount(() => {
		void load();
	});
</script>

<svelte:head><title>Ocene · PDF asistent</title></svelte:head>

<div class="mx-auto max-w-5xl px-4 py-6">
	<h1 class="text-2xl font-semibold">Ocene</h1>
	<p class="mt-1 max-w-3xl text-sm text-gray-600">
		Zadovoljstvo je udeo glasova „za“ među svim glasovima, od svih korisnika. Novi razgovor bira
		svaku komponentu nasumično, srazmerno zadovoljstvu; komponente bez glasova računaju se kao
		potpuno zadovoljavajuće, da bi i nove bile isprobane. Neaktivne komponente se više ne biraju.
	</p>

	{#if error}
		<div class="mt-4">
			<Alert>
				{error}
				<button type="button" class="ml-2 font-medium underline" onclick={load}
					>Pokušaj ponovo</button
				>
			</Alert>
		</div>
	{:else if !scores}
		<p class="mt-8 text-center text-sm text-gray-500">Učitavanje…</p>
	{:else}
		<div class="mt-6 grid gap-4 lg:grid-cols-2">
			{#each SECTIONS as section (section.type)}
				<ScoreChart title={section.title} scores={scores[section.type] ?? []} />
			{/each}
		</div>
	{/if}
</div>
