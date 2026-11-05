<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
</script>

<div class="mx-auto max-w-md px-4 py-16 text-center">
	<h1 class="text-2xl font-semibold">
		{page.status === 404 ? 'Stranica nije pronađena' : 'Došlo je do greške'}
	</h1>
	<p class="mt-2 text-gray-600">
		{page.status}{page.error?.message ? `: ${page.error.message}` : ''}
	</p>
	<a href={resolve('/documents')} class="mt-6 inline-block text-blue-700 hover:underline"
		>Nazad na dokumente</a
	>
</div>
