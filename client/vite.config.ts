import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';

const apiUrl = process.env.API_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Runes mode for our own files; libraries decide for themselves.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// SPA: every route falls back to index.html, the backend serves it.
			adapter: adapter({ fallback: 'index.html' })
		})
	],
	server: {
		// `vite preview` reuses this proxy.
		proxy: { '/api': apiUrl }
	},
	test: {
		include: ['src/**/*.test.ts'],
		environment: 'node',
		expect: { requireAssertions: true }
	}
});
