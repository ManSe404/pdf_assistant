<!--
	Two-step destructive button: the first click arms it ("Sigurno?"), the second one
	confirms. Disarms itself after a few seconds or on Escape. No native dialogs.
-->
<script lang="ts">
	import Icon from './Icon.svelte';

	interface Props {
		label: string;
		confirmLabel?: string;
		/** Accessible name when the button shows only an icon. */
		ariaLabel?: string;
		iconOnly?: boolean;
		disabled?: boolean;
		onConfirm: () => unknown;
		class?: string;
	}

	let {
		label,
		confirmLabel = 'Sigurno?',
		ariaLabel,
		iconOnly = false,
		disabled = false,
		onConfirm,
		class: className = ''
	}: Props = $props();

	let armed = $state(false);
	let running = $state(false);

	$effect(() => {
		if (!armed) {
			return;
		}
		const timer = setTimeout(() => (armed = false), 4000);
		return () => clearTimeout(timer);
	});

	async function handleClick() {
		if (!armed) {
			armed = true;
			return;
		}
		armed = false;
		running = true;
		try {
			await onConfirm();
		} finally {
			running = false;
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && armed) {
			armed = false;
		}
	}
</script>

<button
	type="button"
	class={[
		'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm font-medium transition-colors disabled:opacity-50',
		armed
			? 'bg-red-600 text-white hover:bg-red-700'
			: 'text-gray-600 hover:bg-red-50 hover:text-red-700',
		className
	]}
	disabled={disabled || running}
	aria-label={armed ? `${confirmLabel} ${ariaLabel ?? label}` : (ariaLabel ?? label)}
	title={ariaLabel ?? label}
	onclick={handleClick}
	onkeydown={handleKeydown}
>
	{#if armed}
		{confirmLabel}
	{:else}
		<Icon name="trash" class="size-4" />
		{#if !iconOnly}{label}{/if}
	{/if}
</button>
