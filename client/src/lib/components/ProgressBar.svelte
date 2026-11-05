<script lang="ts">
	interface Props {
		/** 0..1 */
		value: number;
		label: string;
	}

	let { value, label }: Props = $props();

	let percent = $derived(Math.round(Math.min(Math.max(value, 0), 1) * 100));
</script>

<div
	class="h-2 w-full overflow-hidden rounded-full bg-gray-200"
	role="progressbar"
	aria-label={label}
	aria-valuemin={0}
	aria-valuemax={100}
	aria-valuenow={percent}
>
	<div class="h-full bg-blue-600 transition-[width] duration-200" style:width="{percent}%"></div>
</div>
