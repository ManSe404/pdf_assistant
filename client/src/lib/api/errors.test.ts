import { describe, expect, it } from 'vitest';
import {
	ApiError,
	errorMessage,
	inlineError,
	messageOf,
	NETWORK_ERROR,
	parseBody
} from './errors.ts';

describe('errorMessage', () => {
	it('shows a string detail as it is', () => {
		expect(errorMessage(409, { detail: 'Email je već zauzet.' })).toBe('Email je već zauzet.');
		expect(errorMessage(401, { detail: 'Pogrešan email ili lozinka.' })).toBe(
			'Pogrešan email ili lozinka.'
		);
	});

	it('shows the first msg of a 422 validation list', () => {
		const body = {
			detail: [
				{
					type: 'string_too_short',
					loc: ['body', 'password'],
					msg: 'Lozinka mora imati bar 8 znakova.',
					input: 'abc'
				},
				{ type: 'missing', loc: ['body', 'email'], msg: 'Obavezno polje.' }
			]
		};
		expect(errorMessage(422, body)).toBe('Lozinka mora imati bar 8 znakova.');
	});

	it('drops the "Value error, " prefix pydantic adds to custom validators', () => {
		const body = { detail: [{ loc: ['body', 'content'], msg: 'Value error, Pitanje je prazno.' }] };
		expect(errorMessage(422, body)).toBe('Pitanje je prazno.');
	});

	it('skips list items without a msg', () => {
		expect(errorMessage(422, { detail: [{ loc: [] }, { msg: 'Drugo.' }] })).toBe('Drugo.');
	});

	it('falls back to a message for the status when detail is missing or unusable', () => {
		expect(errorMessage(422, { detail: [] })).toBe('Neispravni podaci.');
		expect(errorMessage(404, { detail: '   ' })).toBe('Nije pronađeno.');
		expect(errorMessage(413, null)).toBe('Fajl je prevelik.');
		expect(errorMessage(500, { error: 'x' })).toBe('Greška na serveru (500).');
		expect(errorMessage(502, '<html><body>Bad Gateway</body></html>')).toBe(
			'Greška na serveru (502).'
		);
		expect(errorMessage(418, undefined)).toBe('Došlo je do greške (418).');
		expect(errorMessage(0, null)).toBe(NETWORK_ERROR);
	});

	it('uses a short plain-text body', () => {
		expect(errorMessage(500, 'Internal Server Error')).toBe('Internal Server Error');
	});
});

describe('parseBody', () => {
	it('parses JSON and keeps other text', () => {
		expect(parseBody('{"detail":"x"}')).toEqual({ detail: 'x' });
		expect(parseBody('Internal Server Error')).toBe('Internal Server Error');
		expect(parseBody('')).toBeNull();
	});
});

describe('messageOf', () => {
	it('uses the ApiError message and hides other errors', () => {
		expect(messageOf(new ApiError(409, 'PDF još nije spreman.'))).toBe('PDF još nije spreman.');
		expect(messageOf(new TypeError('x is undefined'))).toBe('Došlo je do neočekivane greške.');
	});
});

describe('inlineError', () => {
	it('stays empty for errors the global alert already shows', () => {
		expect(inlineError(new ApiError(500, 'Greška na serveru (500).'))).toBe('');
		expect(inlineError(new ApiError(0, NETWORK_ERROR))).toBe('');
		expect(inlineError(new ApiError(409, 'PDF još nije spreman.'))).toBe('PDF još nije spreman.');
	});
});
