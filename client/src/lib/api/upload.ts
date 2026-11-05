// PDF upload with XMLHttpRequest, because `fetch` cannot report upload progress.

import { API_BASE, failure } from './client.ts';
import { parseBody } from './errors.ts';
import type { Pdf } from './types.ts';

/** The server enforces its own limit too; this only saves a pointless upload. */
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

/** Returns why the file cannot be uploaded, or null when it looks fine. */
export async function checkPdfFile(file: File): Promise<string | null> {
	const looksLikePdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
	if (!looksLikePdf) {
		return 'Izaberite PDF fajl.';
	}
	if (file.size === 0) {
		return 'Fajl je prazan.';
	}
	if (file.size > MAX_UPLOAD_BYTES) {
		return 'Fajl je veći od 50 MB.';
	}
	// A PDF has the "%PDF-" marker within its first 1024 bytes.
	const head = await file.slice(0, 1024).text();
	if (!head.includes('%PDF-')) {
		return 'Fajl nije ispravan PDF.';
	}
	return null;
}

/**
 * Uploads a PDF. `onProgress` gets the sent fraction (0..1). Rejects with `ApiError`
 * on failure and with an `AbortError` when `signal` is aborted.
 */
export function uploadPdf(
	file: File,
	onProgress: (fraction: number) => void,
	signal?: AbortSignal
): Promise<Pdf> {
	const path = '/pdfs';
	return new Promise((resolve, reject) => {
		if (signal?.aborted) {
			reject(new DOMException('Otpremanje je otkazano.', 'AbortError'));
			return;
		}

		const xhr = new XMLHttpRequest();
		xhr.open('POST', API_BASE + path);
		xhr.setRequestHeader('Accept', 'application/json');

		xhr.upload.addEventListener('progress', (event) => {
			if (event.lengthComputable && event.total > 0) {
				onProgress(event.loaded / event.total);
			}
		});

		xhr.addEventListener('load', () => {
			const body = parseBody(xhr.responseText);
			if (xhr.status >= 200 && xhr.status < 300) {
				onProgress(1);
				resolve(body as Pdf);
			} else {
				reject(failure(path, xhr.status, body));
			}
		});
		xhr.addEventListener('error', () => reject(failure(path, 0, null)));
		xhr.addEventListener('abort', () =>
			reject(new DOMException('Otpremanje je otkazano.', 'AbortError'))
		);
		signal?.addEventListener('abort', () => xhr.abort(), { once: true });

		const form = new FormData();
		form.append('file', file);
		xhr.send(form);
	});
}
