<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { auth } from '../state/auth.svelte.ts';
	import { documents } from '../state/documents.svelte.ts';
	import Icon from './Icon.svelte';

	let signingOut = $state(false);

	let routeId = $derived(page.route.id);

	const linkStyle =
		'inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-gray-600 hover:bg-gray-100 hover:text-gray-900 aria-[current=page]:bg-blue-50 aria-[current=page]:text-blue-700';

	async function signOut() {
		signingOut = true;
		try {
			await auth.signOut();
			documents.reset();
			await goto(resolve('/auth/signin'));
		} catch {
			// The alert shows why; stay signed in.
		} finally {
			signingOut = false;
		}
	}
</script>

<header class="sticky top-0 z-40 h-14 border-b border-gray-200 bg-white">
	<nav class="mx-auto flex h-full max-w-7xl items-center gap-2 px-4" aria-label="Glavna navigacija">
		<a
			href={resolve('/documents')}
			class="mr-auto flex items-center gap-2 rounded-md font-semibold text-gray-900"
		>
			<Icon name="document" class="size-6 text-blue-600" />
			<span class="hidden sm:inline">PDF asistent</span>
		</a>

		{#if auth.user}
			<div class="flex items-center gap-1 text-sm">
				<a
					href={resolve('/documents')}
					class={linkStyle}
					aria-current={routeId === '/documents' || routeId === '/documents/[id]'
						? 'page'
						: undefined}
				>
					<Icon name="document" class="size-4" />
					<span class="sr-only sm:not-sr-only">Dokumenti</span>
				</a>
				<a
					href={resolve('/documents/new')}
					class={linkStyle}
					aria-current={routeId === '/documents/new' ? 'page' : undefined}
				>
					<Icon name="upload" class="size-4" />
					<span class="sr-only sm:not-sr-only">Otpremi PDF</span>
				</a>
				<a
					href={resolve('/scores')}
					class={linkStyle}
					aria-current={routeId === '/scores' ? 'page' : undefined}
				>
					<Icon name="chart" class="size-4" />
					<span class="sr-only sm:not-sr-only">Ocene</span>
				</a>
				<span
					class="ml-2 hidden max-w-48 truncate text-gray-500 lg:inline"
					title="Prijavljeni ste kao {auth.user.email}">{auth.user.email}</span
				>
				<button
					type="button"
					class="{linkStyle} disabled:opacity-50"
					onclick={signOut}
					disabled={signingOut}
				>
					<Icon name="logout" class="size-4" />
					<span class="sr-only sm:not-sr-only">Odjava</span>
				</button>
			</div>
		{:else}
			<div class="flex items-center gap-1 text-sm">
				<a
					href={resolve('/auth/signin')}
					class={linkStyle}
					aria-current={routeId === '/auth/signin' ? 'page' : undefined}>Prijava</a
				>
				<a
					href={resolve('/auth/signup')}
					class={linkStyle}
					aria-current={routeId === '/auth/signup' ? 'page' : undefined}>Registracija</a
				>
			</div>
		{/if}
	</nav>
</header>
