<script lang="ts">
	import { tick } from 'svelte';
	import { MediaQuery } from 'svelte/reactivity';
	import { resolve } from '$app/paths';
	import { api, API_BASE } from '#lib/api/client.ts';
	import { ApiError, messageOf } from '#lib/api/errors.ts';
	import type { Pdf } from '#lib/api/types.ts';
	import Alert from '#lib/components/Alert.svelte';
	import ChatPanel from '#lib/components/chat/ChatPanel.svelte';
	import PdfViewer from '#lib/components/pdf/PdfViewer.svelte';
	import StatusBadge from '#lib/components/StatusBadge.svelte';
	import { ChatSession } from '#lib/state/chat.svelte.ts';
	import type { PageProps } from './$types';

	const POLL_MS = 2000;
	const TABS = [
		{ id: 'chat', label: 'Razgovor' },
		{ id: 'pdf', label: 'PDF' }
	] as const;

	let { params }: PageProps = $props();

	let pdf = $state<Pdf | null>(null);
	let pdfError = $state('');
	let notFound = $state(false);
	let tab = $state<'chat' | 'pdf'>('chat');
	let viewer = $state<ReturnType<typeof PdfViewer>>();

	// Side by side from `lg` up; tabs below that.
	const wide = new MediaQuery('min-width: 1024px');

	let chat = $derived(new ChatSession(params.id));
	let fileUrl = $derived(`${API_BASE}/pdfs/${params.id}/file`);

	$effect(() => {
		const session = chat;
		void session.load();
		return () => session.dispose();
	});

	// Load the PDF's metadata; poll while it is still being indexed.
	$effect(() => {
		const id = params.id;
		let stopped = false;
		let timer: ReturnType<typeof setTimeout> | undefined;

		pdf = null;
		pdfError = '';
		notFound = false;

		async function poll() {
			try {
				const fresh = await api.get<Pdf>(`/pdfs/${id}`);
				if (stopped) {
					return;
				}
				pdf = fresh;
				pdfError = '';
				if (fresh.status === 'processing') {
					timer = setTimeout(poll, POLL_MS);
				}
			} catch (error) {
				if (stopped) {
					return;
				}
				notFound = error instanceof ApiError && error.status === 404;
				pdfError = messageOf(error);
				// A hiccup while waiting for indexing must not freeze the page on
				// "processing": keep asking, a little slower.
				if (pdf?.status === 'processing' && !notFound) {
					timer = setTimeout(poll, POLL_MS * 2);
				}
			}
		}

		void poll();
		return () => {
			stopped = true;
			clearTimeout(timer);
		};
	});

	async function showPage(page: number) {
		if (!wide.current && tab !== 'pdf') {
			tab = 'pdf';
			await tick();
		}
		viewer?.scrollToPage(page);
	}

	function handleTabKeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
			event.preventDefault();
			tab = tab === 'chat' ? 'pdf' : 'chat';
			document.getElementById(`tab-${tab}`)?.focus();
		}
	}
</script>

<svelte:head><title>{pdf?.name ?? 'Dokument'} · PDF asistent</title></svelte:head>

{#if notFound}
	<div class="mx-auto max-w-md px-4 py-16 text-center">
		<h1 class="text-xl font-semibold">Dokument nije pronađen</h1>
		<p class="mt-2 text-sm text-gray-600">Možda je obrisan.</p>
		<a href={resolve('/documents')} class="mt-6 inline-block text-blue-700 hover:underline"
			>Nazad na dokumente</a
		>
	</div>
{:else if pdfError && !pdf}
	<div class="mx-auto max-w-md px-4 py-16">
		<Alert>{pdfError}</Alert>
	</div>
{:else if !pdf}
	<p class="py-16 text-center text-sm text-gray-500">Učitavanje dokumenta…</p>
{:else}
	<div class="flex h-[calc(100dvh-3.5rem)] flex-col">
		<h1 class="sr-only">{pdf.name}</h1>

		{#if pdf.status !== 'ready'}
			<div
				class={[
					'flex flex-wrap items-center gap-2 border-b px-4 py-2 text-sm',
					pdf.status === 'failed'
						? 'border-red-200 bg-red-50 text-red-800'
						: 'border-amber-200 bg-amber-50 text-amber-900'
				]}
				role="status"
			>
				<StatusBadge status={pdf.status} />
				{#if pdf.status === 'processing'}
					Dokument se obrađuje. Pitanja ćete moći da postavljate čim bude spreman.
				{:else}
					{pdf.error ?? 'Obrada nije uspela.'}
				{/if}
			</div>
		{/if}

		<div
			class="flex shrink-0 border-b border-gray-200 bg-white lg:hidden"
			role="tablist"
			aria-label="Prikaz"
		>
			{#each TABS as item (item.id)}
				<button
					type="button"
					role="tab"
					id="tab-{item.id}"
					aria-selected={tab === item.id}
					aria-controls="panel-{item.id}"
					tabindex={tab === item.id ? 0 : -1}
					class="flex-1 border-b-2 px-4 py-2 text-sm font-medium aria-selected:border-blue-600 aria-selected:text-blue-700 aria-[selected=false]:border-transparent aria-[selected=false]:text-gray-600"
					onclick={() => (tab = item.id)}
					onkeydown={handleTabKeydown}
				>
					{item.label}
				</button>
			{/each}
		</div>

		<!-- minmax(0, …): a wide PDF page must not widen its column (the viewer fits pages to it). -->
		<div class="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(22rem,2fr)_minmax(0,3fr)]">
			<div
				id="panel-chat"
				role="tabpanel"
				aria-labelledby="tab-chat"
				class={[
					'min-h-0 min-w-0 border-gray-200 lg:block lg:border-r',
					tab === 'chat' ? 'block' : 'hidden'
				]}
			>
				<ChatPanel {chat} {pdf} onPage={showPage} />
			</div>
			<div
				id="panel-pdf"
				role="tabpanel"
				aria-labelledby="tab-pdf"
				class={['min-h-0 min-w-0 lg:block', tab === 'pdf' ? 'block' : 'hidden']}
			>
				<PdfViewer bind:this={viewer} url={fileUrl} title={pdf.name} />
			</div>
		</div>
	</div>
{/if}
