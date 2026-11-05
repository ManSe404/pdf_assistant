// pdf.js is large, so it is loaded on first use. Vite bundles the worker as a file
// of its own (the `?url` import); nothing comes from a CDN.

import type * as Pdfjs from 'pdfjs-dist';

let loading: Promise<typeof Pdfjs> | null = null;

export function loadPdfjs(): Promise<typeof Pdfjs> {
	loading ??= Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url')])
		.then(([pdfjs, worker]) => {
			pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
			return pdfjs;
		})
		.catch((error: unknown) => {
			// Allow a retry, for example after a deploy replaced the chunk files.
			loading = null;
			throw error;
		});
	return loading;
}
