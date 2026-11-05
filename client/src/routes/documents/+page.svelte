<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { inlineError } from '#lib/api/errors.ts';
	import type { Pdf } from '#lib/api/types.ts';
	import Alert from '#lib/components/Alert.svelte';
	import ConfirmButton from '#lib/components/ConfirmButton.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import StatusBadge from '#lib/components/StatusBadge.svelte';
	import { formatDateTime, formatSize } from '#lib/format.ts';
	import { documents } from '#lib/state/documents.svelte.ts';

	const POLL_MS = 2000;

	let deleteError = $state('');

	onMount(() => {
		void documents.refresh();
	});

	// Poll while anything is still being indexed.
	$effect(() => {
		if (!documents.processing) {
			return;
		}
		const timer = setInterval(() => void documents.refresh(), POLL_MS);
		return () => clearInterval(timer);
	});

	async function remove(pdf: Pdf) {
		deleteError = '';
		try {
			await documents.remove(pdf.id);
		} catch (error) {
			deleteError = inlineError(error);
		}
	}
</script>

<svelte:head><title>Dokumenti · PDF asistent</title></svelte:head>

<div class="mx-auto max-w-5xl px-4 py-6">
	<div class="flex items-center justify-between gap-4">
		<h1 class="text-2xl font-semibold">Dokumenti</h1>
		<a
			href={resolve('/documents/new')}
			class="inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-700"
		>
			<Icon name="upload" class="size-4" />
			Otpremi PDF
		</a>
	</div>

	<div class="mt-4 grid gap-2">
		{#if documents.error}
			<Alert>
				{documents.error}
				<button type="button" class="ml-2 font-medium underline" onclick={() => documents.refresh()}
					>Pokušaj ponovo</button
				>
			</Alert>
		{/if}
		{#if deleteError}
			<Alert onDismiss={() => (deleteError = '')}>{deleteError}</Alert>
		{/if}
	</div>

	{#if !documents.loaded}
		<p class="mt-8 text-center text-sm text-gray-500">Učitavanje…</p>
	{:else if documents.items.length === 0 && !documents.error}
		<div
			class="mt-8 rounded-xl border border-dashed border-gray-300 bg-white px-6 py-12 text-center"
		>
			<Icon name="document" class="mx-auto size-10 text-gray-400" />
			<p class="mt-3 font-medium">Još nema dokumenata.</p>
			<p class="mt-1 text-sm text-gray-600">
				<a href={resolve('/documents/new')} class="text-blue-700 hover:underline">Otpremite PDF</a>
				i postavljajte pitanja o njemu.
			</p>
		</div>
	{:else if documents.items.length}
		<ul
			class="mt-4 divide-y divide-gray-200 overflow-hidden rounded-xl border border-gray-200 bg-white"
			aria-label="Lista dokumenata"
		>
			{#each documents.items as pdf (pdf.id)}
				<li class="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:flex-nowrap">
					<Icon name="document" class="hidden size-6 shrink-0 text-gray-400 sm:block" />
					<div class="min-w-0 flex-1 basis-full sm:basis-auto">
						<a
							href={resolve('/documents/[id]', { id: pdf.id })}
							class="block truncate font-medium text-gray-900 hover:text-blue-700 hover:underline"
							title={pdf.name}>{pdf.name}</a
						>
						<p class="text-xs text-gray-500">
							{formatDateTime(pdf.created_at)} · {formatSize(pdf.size_bytes)}
							{#if pdf.pages}· {pdf.pages} str.{/if}
						</p>
						{#if pdf.status === 'failed'}
							<p class="mt-1 text-sm text-red-700">{pdf.error ?? 'Obrada nije uspela.'}</p>
						{/if}
					</div>
					<StatusBadge status={pdf.status} />
					<ConfirmButton
						label="Obriši"
						ariaLabel="Obriši {pdf.name}"
						onConfirm={() => remove(pdf)}
					/>
				</li>
			{/each}
		</ul>
	{/if}
</div>
