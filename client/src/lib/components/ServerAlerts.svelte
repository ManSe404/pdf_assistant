<!-- 5xx responses and an unreachable server, stacked in a corner until dismissed. -->
<script lang="ts">
	import { alerts } from '../state/alerts.svelte.ts';
	import Alert from './Alert.svelte';
</script>

{#if alerts.items.length}
	<div
		class="fixed inset-x-4 bottom-4 z-50 flex flex-col gap-2 sm:left-auto sm:w-96"
		aria-label="Greške servera"
	>
		{#each alerts.items as item (item.id)}
			<Alert kind="error" class="shadow-lg" onDismiss={() => alerts.dismiss(item.id)}>
				{item.message}
			</Alert>
		{/each}
	</div>
{/if}
