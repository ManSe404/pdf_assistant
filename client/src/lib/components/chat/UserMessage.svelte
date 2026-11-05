<script lang="ts">
	let { content }: { content: string } = $props();
</script>

<div
	class="max-w-[85%] self-end rounded-lg rounded-tr-sm bg-blue-600 px-3 py-2 text-sm whitespace-pre-wrap break-words text-white"
>
	{content}
</div>
