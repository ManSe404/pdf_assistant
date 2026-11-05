<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { isAbortError } from '#lib/api/client.ts';
	import { inlineError } from '#lib/api/errors.ts';
	import { checkPdfFile, uploadPdf } from '#lib/api/upload.ts';
	import Alert from '#lib/components/Alert.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import ProgressBar from '#lib/components/ProgressBar.svelte';
	import { formatPercent, formatSize } from '#lib/format.ts';
	import { documents } from '#lib/state/documents.svelte.ts';

	let file = $state<File | null>(null);
	let error = $state('');
	/** Sent fraction while uploading, null otherwise. */
	let progress = $state<number | null>(null);
	let controller: AbortController | null = null;

	onMount(() => () => controller?.abort());

	async function handleChange(event: Event & { currentTarget: HTMLInputElement }) {
		const input = event.currentTarget;
		const chosen = input.files?.[0] ?? null;
		file = null;
		error = '';
		if (!chosen) {
			return;
		}
		const problem = await checkPdfFile(chosen);
		if (problem) {
			error = problem;
			input.value = '';
			return;
		}
		file = chosen;
	}

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (!file) {
			error = 'Izaberite PDF fajl.';
			return;
		}
		error = '';
		progress = 0;
		controller = new AbortController();
		try {
			const pdf = await uploadPdf(file, (fraction) => (progress = fraction), controller.signal);
			documents.add(pdf);
			await goto(resolve('/documents'));
		} catch (caught) {
			progress = null;
			if (!isAbortError(caught)) {
				error = inlineError(caught);
			}
		} finally {
			controller = null;
		}
	}
</script>

<svelte:head><title>Otpremi PDF · PDF asistent</title></svelte:head>

<div class="mx-auto w-full max-w-lg px-4 py-8">
	<h1 class="text-2xl font-semibold">Otpremi PDF</h1>
	<p class="mt-1 text-sm text-gray-600">
		Najviše 50 MB. Posle otpremanja dokument se obrađuje, pa pitanja možete postavljati kad bude
		spreman.
	</p>

	<form
		class="mt-6 grid gap-4 rounded-xl border border-gray-200 bg-white p-6"
		onsubmit={handleSubmit}
		novalidate
	>
		<div class="grid gap-1.5">
			<label for="file" class="text-sm font-medium">PDF fajl</label>
			<input
				id="file"
				name="file"
				type="file"
				accept="application/pdf,.pdf"
				disabled={progress !== null}
				onchange={handleChange}
				aria-describedby={error ? 'upload-error' : undefined}
				class="block w-full rounded-md border border-gray-300 text-sm text-gray-700 file:mr-4 file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:font-semibold file:text-blue-700 hover:file:bg-blue-100 disabled:opacity-60"
			/>
			{#if file}
				<p class="text-xs text-gray-500">{file.name} · {formatSize(file.size)}</p>
			{/if}
		</div>

		{#if progress !== null}
			<div class="grid gap-1.5">
				<ProgressBar value={progress} label="Otpremanje" />
				<p class="text-xs text-gray-600" aria-live="polite">
					{progress < 1 ? `Otpremanje… ${formatPercent(progress)}` : 'Čuvanje na serveru…'}
				</p>
			</div>
		{/if}

		{#if error}
			<div id="upload-error"><Alert>{error}</Alert></div>
		{/if}

		<div class="flex gap-2">
			<button
				type="submit"
				class="inline-flex flex-1 items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60"
				disabled={!file || progress !== null}
			>
				<Icon name="upload" class="size-4" />
				Otpremi
			</button>
			{#if progress !== null}
				<button
					type="button"
					class="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
					onclick={() => controller?.abort()}>Otkaži</button
				>
			{/if}
		</div>
	</form>
</div>
