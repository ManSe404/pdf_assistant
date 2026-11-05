<script lang="ts">
	import type { PdfStatus } from '../api/types.ts';

	let { status }: { status: PdfStatus } = $props();

	const badges = {
		processing: { text: 'Obrađuje se', style: 'bg-amber-50 text-amber-800 ring-amber-200' },
		ready: { text: 'Spreman', style: 'bg-green-50 text-green-800 ring-green-200' },
		failed: { text: 'Greška', style: 'bg-red-50 text-red-800 ring-red-200' }
	};

	let badge = $derived(badges[status]);
</script>

<span
	class={[
		'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset',
		badge.style
	]}
>
	{#if status === 'processing'}
		<span
			class="size-2.5 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none"
			aria-hidden="true"
		></span>
	{/if}
	{badge.text}
</span>
