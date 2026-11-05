<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';

	interface Props {
		kind?: 'error' | 'warning' | 'info' | 'success';
		/** Shows a close button when set. */
		onDismiss?: () => void;
		class?: string;
		children: Snippet;
	}

	let { kind = 'error', onDismiss, class: className = '', children }: Props = $props();

	const styles = {
		error: 'border-red-200 bg-red-50 text-red-800',
		warning: 'border-amber-200 bg-amber-50 text-amber-900',
		info: 'border-blue-200 bg-blue-50 text-blue-800',
		success: 'border-green-200 bg-green-50 text-green-800'
	};
</script>

<div
	class={['flex items-start gap-3 rounded-md border px-3 py-2 text-sm', styles[kind], className]}
	role={kind === 'error' ? 'alert' : 'status'}
>
	<div class="min-w-0 flex-1 break-words">{@render children()}</div>
	{#if onDismiss}
		<button
			type="button"
			class="-mr-1 rounded p-0.5 opacity-70 hover:opacity-100"
			onclick={onDismiss}
			aria-label="Zatvori"
			title="Zatvori"
		>
			<Icon name="close" class="size-4" />
		</button>
	{/if}
</div>
