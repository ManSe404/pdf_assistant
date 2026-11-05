<!-- Sign-in and sign-up form; both end on the page the user originally asked for. -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import type { Path } from '$app/types';
	import { inlineError } from '../api/errors.ts';
	import { auth } from '../state/auth.svelte.ts';
	import Alert from './Alert.svelte';

	let { mode }: { mode: 'signin' | 'signup' } = $props();

	let email = $state('');
	let password = $state('');
	let passwordAgain = $state('');
	let error = $state('');
	let submitting = $state(false);

	let signUp = $derived(mode === 'signup');

	const inputStyle =
		'block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-xs focus:border-blue-600';

	/** The `next` query parameter, if it points inside this app. */
	function nextPath(): Path {
		const next = page.url.searchParams.get('next');
		if (next) {
			const url = new URL(next, page.url.origin);
			if (url.origin === page.url.origin && !url.pathname.startsWith('/auth/')) {
				return (url.pathname.slice(1) + url.search) as Path;
			}
		}
		return 'documents';
	}

	function validate(): string {
		if (!email.trim()) {
			return 'Unesite email.';
		}
		if (!password) {
			return 'Unesite lozinku.';
		}
		if (!signUp) {
			return '';
		}
		// The server limits passwords to 8..72 bytes (bcrypt), not characters.
		const bytes = new TextEncoder().encode(password).length;
		if (bytes < 8) {
			return 'Lozinka mora imati najmanje 8 znakova.';
		}
		if (bytes > 72) {
			return 'Lozinka je predugačka (najviše 72 bajta).';
		}
		if (password !== passwordAgain) {
			return 'Lozinke se ne poklapaju.';
		}
		return '';
	}

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		error = validate();
		if (error) {
			return;
		}
		submitting = true;
		try {
			if (signUp) {
				await auth.signUp(email.trim(), password);
			} else {
				await auth.signIn(email.trim(), password);
			}
			await goto(resolve(nextPath()));
		} catch (caught) {
			error = inlineError(caught);
		} finally {
			submitting = false;
		}
	}
</script>

<div class="mx-auto w-full max-w-sm px-4 py-12">
	<div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
		<h1 class="text-center text-2xl font-semibold">{signUp ? 'Registracija' : 'Prijava'}</h1>
		<p class="mt-2 text-center text-sm text-gray-600">
			{#if signUp}
				Već imate nalog?
				<a href={resolve('/auth/signin')} class="font-medium text-blue-700 hover:underline"
					>Prijavite se</a
				>
			{:else}
				Nemate nalog?
				<a href={resolve('/auth/signup')} class="font-medium text-blue-700 hover:underline"
					>Registrujte se</a
				>
			{/if}
		</p>

		<!-- novalidate: errors show inline, not as browser bubbles. -->
		<form class="mt-6 grid gap-4" onsubmit={handleSubmit} novalidate>
			<div class="grid gap-1.5">
				<label for="email" class="text-sm font-medium">Email</label>
				<input
					id="email"
					type="email"
					autocomplete="email"
					required
					class={inputStyle}
					bind:value={email}
				/>
			</div>

			<div class="grid gap-1.5">
				<label for="password" class="text-sm font-medium">Lozinka</label>
				<input
					id="password"
					type="password"
					autocomplete={signUp ? 'new-password' : 'current-password'}
					required
					aria-describedby={signUp ? 'password-hint' : undefined}
					class={inputStyle}
					bind:value={password}
				/>
				{#if signUp}
					<p id="password-hint" class="text-xs text-gray-500">Najmanje 8 znakova.</p>
				{/if}
			</div>

			{#if signUp}
				<div class="grid gap-1.5">
					<label for="password-again" class="text-sm font-medium">Ponovite lozinku</label>
					<input
						id="password-again"
						type="password"
						autocomplete="new-password"
						required
						class={inputStyle}
						bind:value={passwordAgain}
					/>
				</div>
			{/if}

			{#if error}
				<Alert>{error}</Alert>
			{/if}

			<button
				type="submit"
				class="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60"
				disabled={submitting}
			>
				{#if submitting}
					{signUp ? 'Registrovanje…' : 'Prijavljivanje…'}
				{:else}
					{signUp ? 'Registruj se' : 'Prijavi se'}
				{/if}
			</button>
		</form>
	</div>
</div>
