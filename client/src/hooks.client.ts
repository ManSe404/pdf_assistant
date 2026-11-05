import { goto } from '$app/navigation';
import { resolve } from '$app/paths';
import type { ClientInit } from '@sveltejs/kit/hooks';
import { configureApi } from '#lib/api/client.ts';
import { alerts } from '#lib/state/alerts.svelte.ts';
import { auth } from '#lib/state/auth.svelte.ts';
import { documents } from '#lib/state/documents.svelte.ts';

export const init: ClientInit = () => {
	configureApi({
		// Any 401: the session is gone, so sign in again and come back here afterwards.
		onUnauthorized: () => {
			auth.forget();
			documents.reset();
			const { pathname, search } = window.location;
			if (!pathname.startsWith('/auth/')) {
				void goto(resolve(`/auth/signin?next=${encodeURIComponent(pathname + search)}`));
			}
		},
		onServerError: (message) => alerts.push(message)
	});
};
