import { redirect } from '@sveltejs/kit';
import { resolve } from '$app/paths';
import { auth } from '#lib/state/auth.svelte.ts';
import type { LayoutLoad } from './$types';

// A client-only SPA: adapter-static writes index.html as the fallback for every route.
export const ssr = false;

export const load: LayoutLoad = async ({ url, fetch }) => {
	const user = await auth.load(fetch);
	const onAuthPage = url.pathname.startsWith('/auth/');
	if (!user && !onAuthPage) {
		const next = url.pathname + url.search;
		redirect(
			307,
			next === '/'
				? resolve('/auth/signin')
				: resolve(`/auth/signin?next=${encodeURIComponent(next)}`)
		);
	}
	if (user && onAuthPage) {
		redirect(307, resolve('/documents'));
	}
};
