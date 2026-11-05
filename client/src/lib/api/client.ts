// A small `fetch` wrapper for the backend under `/api`. The session is an httpOnly
// cookie, so the default `credentials: 'same-origin'` is all that is needed.

import { ApiError, errorMessage, parseBody } from './errors.ts';

export const API_BASE = '/api';

/** Ordinary JSON calls give up after this long; streams and uploads have no limit. */
const JSON_TIMEOUT_MS = 30_000;

const TIMEOUT_ERROR = 'Server ne odgovara. Pokušajte ponovo.';

/** Paths where 401 means "wrong email or password", not "session expired". */
const CREDENTIAL_PATHS = new Set(['/auth/signin', '/auth/signup']);

interface Hooks {
	/** Any 401 outside the sign-in and sign-up forms. */
	onUnauthorized: () => void;
	/** 5xx responses and unreachable server. */
	onServerError: (message: string) => void;
}

let hooks: Hooks = { onUnauthorized: () => {}, onServerError: () => {} };

/** Wires the API layer to the UI (navigation and alerts); called once by the root layout. */
export function configureApi(next: Partial<Hooks>) {
	hooks = { ...hooks, ...next };
}

/** Reports a failed response to the hooks and returns the error to throw. */
export function failure(path: string, status: number, body: unknown): ApiError {
	const message = errorMessage(status, body);
	if (status === 401 && !CREDENTIAL_PATHS.has(path)) {
		hooks.onUnauthorized();
	}
	if (status >= 500 || status === 0) {
		hooks.onServerError(message);
	}
	return new ApiError(status, message);
}

export function isAbortError(error: unknown): boolean {
	return error instanceof DOMException && error.name === 'AbortError';
}

export interface RequestOptions {
	body?: unknown;
	signal?: AbortSignal;
	timeoutMs?: number;
	/** The `fetch` of a SvelteKit `load` function, when called from one. */
	fetch?: typeof globalThis.fetch;
}

/** Sends a request and returns the response if it is 2xx; throws `ApiError` otherwise. */
export async function send(
	method: string,
	path: string,
	{ body, signal, timeoutMs, fetch = globalThis.fetch }: RequestOptions = {}
): Promise<Response> {
	const headers: Record<string, string> = { Accept: 'application/json' };
	let payload: BodyInit | undefined;
	if (body instanceof FormData) {
		payload = body;
	} else if (body !== undefined) {
		payload = JSON.stringify(body);
		headers['Content-Type'] = 'application/json';
	}

	const signals = [signal, timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined].filter(
		(s): s is AbortSignal => s !== undefined
	);

	let response: Response;
	try {
		response = await fetch(API_BASE + path, {
			method,
			headers,
			body: payload,
			signal: signals.length ? AbortSignal.any(signals) : undefined
		});
	} catch (error) {
		if (isAbortError(error) && signal?.aborted) {
			throw error;
		}
		if (error instanceof DOMException && error.name === 'TimeoutError') {
			hooks.onServerError(TIMEOUT_ERROR);
			throw new ApiError(0, TIMEOUT_ERROR);
		}
		throw failure(path, 0, null);
	}

	if (!response.ok) {
		const text = await response.text().catch(() => '');
		throw failure(path, response.status, parseBody(text));
	}
	return response;
}

async function json<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
	const response = await send(method, path, { timeoutMs: JSON_TIMEOUT_MS, ...options });
	const text = await response.text();
	return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
	get: <T>(path: string, options?: RequestOptions) => json<T>('GET', path, options),
	post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
		json<T>('POST', path, { ...options, body }),
	put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
		json<T>('PUT', path, { ...options, body }),
	delete: (path: string, options?: RequestOptions) => json<void>('DELETE', path, options)
};
