// Turning failed responses into one Serbian sentence for the user. Pure functions,
// no DOM and no SvelteKit imports, so they are easy to test.

/** A failed API call. `status` is 0 when the server could not be reached at all. */
export class ApiError extends Error {
	readonly status: number;

	constructor(status: number, message: string) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
	}
}

export const NETWORK_ERROR = 'Server nije dostupan. Proverite vezu i pokušajte ponovo.';

const FALLBACKS: Record<number, string> = {
	0: NETWORK_ERROR,
	400: 'Neispravan zahtev.',
	401: 'Niste prijavljeni.',
	403: 'Pristup nije dozvoljen.',
	404: 'Nije pronađeno.',
	409: 'Zahtev trenutno nije moguć.',
	413: 'Fajl je prevelik.',
	422: 'Neispravni podaci.'
};

/** Parses a response body as JSON when it is JSON, otherwise returns the text itself. */
export function parseBody(text: string): unknown {
	if (!text) {
		return null;
	}
	try {
		return JSON.parse(text);
	} catch {
		return text;
	}
}

/**
 * The message to show for a failed response.
 *
 * FastAPI answers `{"detail": "..."}`, or for 422 validation errors
 * `{"detail": [{"msg": "...", ...}, ...]}`, of which the first `msg` is shown.
 * Anything else falls back to a generic message for the status code.
 */
export function errorMessage(status: number, body: unknown): string {
	const detail = isRecord(body) ? body.detail : undefined;

	if (typeof detail === 'string' && detail.trim()) {
		return detail.trim();
	}

	if (Array.isArray(detail)) {
		const first = detail.find((item) => isRecord(item) && typeof item.msg === 'string');
		if (first && isRecord(first) && typeof first.msg === 'string' && first.msg.trim()) {
			// Pydantic prefixes messages of custom validators with "Value error, ".
			return first.msg.trim().replace(/^Value error,\s*/, '');
		}
	}

	// A short plain-text body (for example from a proxy) is still better than nothing;
	// HTML error pages are not shown.
	if (typeof body === 'string') {
		const text = body.trim();
		if (text && text.length <= 300 && !text.startsWith('<')) {
			return text;
		}
	}

	return fallbackMessage(status);
}

export function fallbackMessage(status: number): string {
	if (FALLBACKS[status]) {
		return FALLBACKS[status];
	}
	if (status >= 500) {
		return `Greška na serveru (${status}).`;
	}
	return `Došlo je do greške (${status}).`;
}

/** The user-facing message of anything caught in a `catch` block. */
export function messageOf(error: unknown): string {
	if (error instanceof ApiError) {
		return error.message;
	}
	return 'Došlo je do neočekivane greške.';
}

/** True when the error already shows as a global alert (5xx or unreachable server). */
export function isAlerted(error: unknown): boolean {
	return error instanceof ApiError && (error.status === 0 || error.status >= 500);
}

/**
 * The message for an inline error next to the control that failed, or '' when the
 * global alert already shows it (so the same message does not appear twice).
 */
export function inlineError(error: unknown): string {
	return isAlerted(error) ? '' : messageOf(error);
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}
