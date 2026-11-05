<!--
	Scrollable PDF with a selectable text layer. Pages are rendered lazily: only those
	near the viewport get a canvas, and canvases far away are released again, so a
	300-page PDF neither renders everything nor keeps every page in memory.
	Each page wrapper has id `page-N`; `scrollToPage(n)` scrolls there and flashes it.
-->
<script lang="ts">
	import { onMount, tick } from 'svelte';
	import type { Attachment } from 'svelte/attachments';
	import type { PDFDocumentProxy, RenderTask, TextLayer } from 'pdfjs-dist';
	import { failure } from '../../api/client.ts';
	import { loadPdfjs } from './pdfjs.ts';

	interface Props {
		/** URL of the PDF file. */
		url: string;
		/** Shown in the toolbar and used as the region label. */
		title: string;
	}

	let { url, title }: Props = $props();

	/** Canvases kept alive at most (besides those in view). */
	const MAX_RENDERED = 8;
	const MIN_SCALE = 0.4;
	const MAX_SCALE = 2;
	/** Horizontal padding of the page column, in CSS px. */
	const PADDING = 16;

	interface Size {
		width: number;
		height: number;
	}

	interface RenderedPage {
		cancelled: boolean;
		canvas: HTMLCanvasElement | null;
		task: RenderTask | null;
		textLayer: TextLayer | null;
	}

	let scroller = $state<HTMLDivElement>();
	let pdf = $state.raw<PDFDocumentProxy | null>(null);
	let loading = $state(true);
	let error = $state('');
	/** Size of page 1 at scale 1; placeholder for pages not measured yet. */
	let baseSize = $state.raw<Size | null>(null);
	/** Measured sizes (scale 1) of pages that differ from page 1. */
	let sizes = $state<Record<number, Size>>({});
	let scale = $state(1);
	let currentPage = $state(1);
	let flashing = $state<number | null>(null);

	let pageNumbers = $derived(Array.from({ length: pdf?.numPages ?? 0 }, (_, i) => i + 1));

	// Render bookkeeping. Never read by the template, so deliberately not reactive:
	// a reactive Map here would re-run effects on every scroll.
	/* eslint-disable svelte/prefer-svelte-reactivity */
	const layers = new Map<number, HTMLDivElement>();
	const rendered = new Map<number, RenderedPage>();
	const nearby = new Set<number>();
	/* eslint-enable svelte/prefer-svelte-reactivity */
	let lazyObserver: IntersectionObserver | null = null;
	let currentObserver: IntersectionObserver | null = null;
	let renderTimer: ReturnType<typeof setTimeout> | undefined;
	let flashTimer: ReturnType<typeof setTimeout> | undefined;
	/** A scroll request that arrived before the document was loaded. */
	let pendingScroll: number | null = null;

	function sizeOf(n: number): Size | null {
		return sizes[n] ?? baseSize;
	}

	function fitScale(): number {
		// Hidden (the PDF tab on a phone): keep the scale until it is shown.
		if (!scroller || !baseSize || scroller.clientWidth === 0) {
			return scale;
		}
		const available = scroller.clientWidth - 2 * PADDING;
		return Math.min(Math.max(available / baseSize.width, MIN_SCALE), MAX_SCALE);
	}

	// Load the document whenever the URL changes.
	$effect(() => {
		const source = url;
		let cancelled = false;
		let destroy: (() => void) | null = null;

		loading = true;
		error = '';
		pdf = null;
		baseSize = null;
		sizes = {};

		loadPdfjs()
			.then(async (pdfjs) => {
				if (cancelled) {
					return;
				}
				const task = pdfjs.getDocument({ url: source });
				destroy = () => void task.destroy();
				const doc = await task.promise;
				const first = await doc.getPage(1);
				if (cancelled) {
					return;
				}
				const { width, height } = first.getViewport({ scale: 1 });
				baseSize = { width, height };
				pdf = doc;
				scale = fitScale();
				await tick();
				await applyFit();
			})
			.catch((caught: unknown) => {
				if (cancelled) {
					return;
				}
				const status = (caught as { status?: unknown })?.status;
				if (typeof status === 'number' && status > 0) {
					// 401 sends the user to sign in, 5xx raises an alert.
					failure(source, status, null);
				}
				error = 'PDF nije moguće prikazati.';
			})
			.finally(() => {
				if (!cancelled) {
					loading = false;
				}
			});

		return () => {
			cancelled = true;
			for (const n of [...rendered.keys()]) {
				release(n);
			}
			destroy?.();
		};
	});

	onMount(() => {
		if (!scroller) {
			return;
		}
		const root = scroller;

		// Render pages within one screen above or below the visible area.
		lazyObserver = new IntersectionObserver(
			(entries) => {
				for (const entry of entries) {
					const n = Number((entry.target as HTMLElement).dataset.page);
					if (entry.isIntersecting) {
						nearby.add(n);
					} else {
						nearby.delete(n);
					}
				}
				scheduleRender();
			},
			{ root, rootMargin: '100% 0px' }
		);

		// The page crossing a line at 40 % of the height is the "current" one.
		currentObserver = new IntersectionObserver(
			(entries) => {
				for (const entry of entries) {
					if (entry.isIntersecting) {
						currentPage = Number((entry.target as HTMLElement).dataset.page);
					}
				}
			},
			{ root, rootMargin: '-40% 0px -59% 0px' }
		);

		let resizeTimer: ReturnType<typeof setTimeout> | undefined;
		const resizeObserver = new ResizeObserver(() => {
			clearTimeout(resizeTimer);
			resizeTimer = setTimeout(() => void applyFit(), 150);
		});
		resizeObserver.observe(root);

		return () => {
			lazyObserver?.disconnect();
			currentObserver?.disconnect();
			resizeObserver.disconnect();
			clearTimeout(resizeTimer);
			clearTimeout(renderTimer);
			clearTimeout(flashTimer);
		};
	});

	/** Attachment for each page wrapper: watch it and remember its drawing layer. */
	function page(n: number): Attachment<HTMLDivElement> {
		return (wrapper) => {
			const layer = wrapper.querySelector<HTMLDivElement>('[data-layer]');
			if (layer) {
				layers.set(n, layer);
			}
			lazyObserver?.observe(wrapper);
			currentObserver?.observe(wrapper);
			return () => {
				lazyObserver?.unobserve(wrapper);
				currentObserver?.unobserve(wrapper);
				release(n);
				layers.delete(n);
				nearby.delete(n);
			};
		};
	}

	/**
	 * Fits the pages to the current width (re-rendering them when the scale changes)
	 * and carries out a scroll request that waited for the viewer to become visible.
	 */
	async function applyFit() {
		if (!pdf || !scroller || scroller.clientWidth === 0) {
			return;
		}
		const next = fitScale();
		if (Math.abs(next - scale) / scale > 0.02) {
			const anchor = currentPage;
			scale = next;
			for (const n of [...rendered.keys()]) {
				release(n);
			}
			await tick();
			if (pendingScroll === null) {
				jumpTo(anchor, false);
			}
			scheduleRender();
		}
		if (pendingScroll !== null) {
			const n = pendingScroll;
			pendingScroll = null;
			scrollToPage(n);
		}
	}

	/** Debounced: fast scrolling through many pages renders only where it stops. */
	function scheduleRender() {
		clearTimeout(renderTimer);
		renderTimer = setTimeout(renderNearby, 80);
	}

	function renderNearby() {
		for (const n of nearby) {
			void render(n);
		}
		if (rendered.size <= MAX_RENDERED) {
			return;
		}
		const farthestFirst = [...rendered.keys()]
			.filter((n) => !nearby.has(n))
			.sort((a, b) => Math.abs(b - currentPage) - Math.abs(a - currentPage));
		for (const n of farthestFirst) {
			if (rendered.size <= MAX_RENDERED) {
				break;
			}
			release(n);
		}
	}

	async function render(n: number) {
		const layer = layers.get(n);
		if (!pdf || !layer || rendered.has(n)) {
			return;
		}
		const entry: RenderedPage = { cancelled: false, canvas: null, task: null, textLayer: null };
		rendered.set(n, entry);
		const renderScale = scale;

		try {
			const pdfjs = await loadPdfjs();
			const pdfPage = await pdf.getPage(n);
			if (entry.cancelled) {
				return;
			}

			const natural = pdfPage.getViewport({ scale: 1 });
			if (
				baseSize &&
				(Math.abs(natural.width - baseSize.width) > 1 ||
					Math.abs(natural.height - baseSize.height) > 1)
			) {
				sizes[n] = { width: natural.width, height: natural.height };
			}

			const viewport = pdfPage.getViewport({ scale: renderScale });
			// Sharp on HiDPI screens, capped so a page stays a few MB of memory.
			const ratio = Math.min(window.devicePixelRatio || 1, 2);
			const canvas = document.createElement('canvas');
			canvas.width = Math.floor(viewport.width * ratio);
			canvas.height = Math.floor(viewport.height * ratio);
			canvas.className = 'absolute inset-0 h-full w-full';
			canvas.setAttribute('aria-hidden', 'true');
			entry.canvas = canvas;
			layer.append(canvas);

			entry.task = pdfPage.render({
				canvas,
				viewport,
				transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0]
			});
			await entry.task.promise;
			if (entry.cancelled) {
				return;
			}

			const textDiv = document.createElement('div');
			textDiv.className = 'textLayer';
			layer.append(textDiv);
			entry.textLayer = new pdfjs.TextLayer({
				textContentSource: pdfPage.streamTextContent(),
				container: textDiv,
				viewport
			});
			await entry.textLayer.render();
		} catch (caught) {
			if (entry.cancelled) {
				return;
			}
			const name = (caught as { name?: unknown })?.name;
			if (name !== 'RenderingCancelledException') {
				console.warn(`PDF strana ${n} nije iscrtana`, caught);
			}
			// Let a later scroll try again.
			release(n);
		}
	}

	function release(n: number) {
		const entry = rendered.get(n);
		if (!entry) {
			return;
		}
		entry.cancelled = true;
		entry.task?.cancel();
		entry.textLayer?.cancel();
		if (entry.canvas) {
			// Frees the bitmap now instead of at the next garbage collection.
			entry.canvas.width = 0;
			entry.canvas.height = 0;
		}
		layers.get(n)?.replaceChildren();
		rendered.delete(n);
	}

	/** Scrolls the viewer to page `n` (1-based) and briefly highlights it. */
	export function scrollToPage(n: number) {
		if (!pdf || !scroller || scroller.clientWidth === 0) {
			// Not loaded or not visible yet: done by the load or by applyFit().
			pendingScroll = n;
			return;
		}
		const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		// A smooth scroll over dozens of pages takes long and renders nothing useful.
		const far = Math.abs(n - currentPage) > 10;
		if (jumpTo(n, !reduceMotion && !far)) {
			void flash(n);
		}
	}

	function jumpTo(n: number, smooth: boolean): boolean {
		const target = scroller?.querySelector<HTMLElement>(`#page-${n}`);
		if (!scroller || !target) {
			return false;
		}
		scroller.scrollTo({ top: target.offsetTop - PADDING, behavior: smooth ? 'smooth' : 'instant' });
		return true;
	}

	async function flash(n: number) {
		clearTimeout(flashTimer);
		flashing = null;
		await tick();
		flashing = n;
		flashTimer = setTimeout(() => (flashing = null), 1800);
	}
</script>

<section class="flex h-full min-h-0 flex-col bg-gray-100" aria-label="PDF: {title}">
	<div
		class="flex h-10 shrink-0 items-center justify-between gap-3 border-b border-gray-200 bg-white px-3 text-sm"
	>
		<span class="truncate font-medium" {title}>{title}</span>
		{#if pdf}
			<span class="shrink-0 text-gray-500" aria-live="off"
				>Strana {currentPage} / {pdf.numPages}</span
			>
		{/if}
	</div>

	<!-- tabindex: the scroll area must be reachable by keyboard. -->
	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div bind:this={scroller} class="relative min-h-0 flex-1 overflow-auto" tabindex="0">
		{#if loading}
			<p class="p-6 text-center text-sm text-gray-500">Učitavanje PDF-a…</p>
		{:else if error}
			<p class="p-6 text-center text-sm text-red-700" role="alert">{error}</p>
		{/if}

		<div class="flex flex-col items-center gap-4 py-4" style:padding-inline="{PADDING}px">
			{#each pageNumbers as n (n)}
				{@const size = sizeOf(n)}
				<div
					id="page-{n}"
					data-page={n}
					class={['pdf-page relative shrink-0 bg-white shadow-sm', flashing === n && 'flash']}
					style:width="{Math.floor((size?.width ?? 0) * scale)}px"
					style:height="{Math.floor((size?.height ?? 0) * scale)}px"
					style:--scale-factor={scale}
					{@attach page(n)}
				>
					<span
						class="absolute inset-0 grid place-items-center text-sm text-gray-300 select-none"
						aria-hidden="true">{n}</span
					>
					<div data-layer class="absolute inset-0"></div>
				</div>
			{/each}
		</div>
	</div>
</section>
