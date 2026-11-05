<script lang="ts">
	import '../app.css';
	import Navbar from '#lib/components/Navbar.svelte';
	import ServerAlerts from '#lib/components/ServerAlerts.svelte';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<div class="min-h-dvh bg-gray-50 text-gray-900">
	<a
		href="#main"
		class="sr-only rounded-md bg-white px-3 py-2 focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50"
		>Preskoči na sadržaj</a
	>
	<Navbar />
	<main id="main">
		{@render children()}
	</main>
	<ServerAlerts />
</div>
