import { describe, expect, it } from 'vitest';
import { NdjsonError, NdjsonParser, readNdjson } from './ndjson.ts';

function byteStream(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
	return new ReadableStream({
		start(controller) {
			for (const chunk of chunks) {
				controller.enqueue(chunk);
			}
			controller.close();
		}
	});
}

async function collect<T>(iterable: AsyncIterable<T>): Promise<T[]> {
	const values: T[] = [];
	for await (const value of iterable) {
		values.push(value);
	}
	return values;
}

describe('NdjsonParser', () => {
	it('parses several lines from one chunk', () => {
		const parser = new NdjsonParser();
		expect(parser.push('{"a":1}\n{"b":2}\n')).toEqual([{ a: 1 }, { b: 2 }]);
		expect(parser.flush()).toEqual([]);
	});

	it('buffers a line split across chunks until its newline arrives', () => {
		const parser = new NdjsonParser();
		expect(parser.push('{"type":"del')).toEqual([]);
		expect(parser.push('ta","text":"Zdr')).toEqual([]);
		expect(parser.push('avo"}\n{"type":')).toEqual([{ type: 'delta', text: 'Zdravo' }]);
		expect(parser.push('"end"}\n')).toEqual([{ type: 'end' }]);
	});

	it('handles a chunk that is only the newline', () => {
		const parser = new NdjsonParser();
		expect(parser.push('{"n":1}')).toEqual([]);
		expect(parser.push('\n')).toEqual([{ n: 1 }]);
	});

	it('skips blank lines and accepts CRLF line endings', () => {
		const parser = new NdjsonParser();
		expect(parser.push('{"n":1}\r\n\r\n\n{"n":2}\r\n')).toEqual([{ n: 1 }, { n: 2 }]);
	});

	it('marks an invalid unterminated last line as truncated', () => {
		const parser = new NdjsonParser();
		expect(parser.push('{"type":"delta","text":"a"}\n{"type":"del')).toEqual([
			{ type: 'delta', text: 'a' }
		]);
		let caught: unknown;
		try {
			parser.flush();
		} catch (error) {
			caught = error;
		}
		expect(caught).toBeInstanceOf(NdjsonError);
		expect((caught as NdjsonError).truncated).toBe(true);
	});

	it('returns a last line without a trailing newline on flush', () => {
		const parser = new NdjsonParser();
		expect(parser.push('{"n":1}\n{"n":2}')).toEqual([{ n: 1 }]);
		expect(parser.flush()).toEqual([{ n: 2 }]);
		expect(parser.flush()).toEqual([]);
	});

	it('keeps newlines escaped inside JSON strings', () => {
		const parser = new NdjsonParser();
		expect(parser.push('{"text":"red 1\\nred 2"}\n')).toEqual([{ text: 'red 1\nred 2' }]);
	});

	it('throws NdjsonError with the offending line', () => {
		const parser = new NdjsonParser();
		expect(() => parser.push('{"ok":true}\nnot json\n')).toThrow(NdjsonError);

		let caught: unknown;
		try {
			new NdjsonParser().push('{broken\n');
		} catch (error) {
			caught = error;
		}
		expect(caught).toBeInstanceOf(NdjsonError);
		expect((caught as NdjsonError).line).toBe('{broken');
		expect((caught as NdjsonError).truncated).toBe(false);
	});
});

describe('readNdjson', () => {
	it('decodes a multi-byte character split between chunks', async () => {
		const bytes = new TextEncoder().encode('{"text":"čćšžđ"}\n');
		// "č" is two bytes in UTF-8; cut between them.
		const cut = bytes.indexOf(0xc4) + 1;
		const events = await collect(readNdjson(byteStream([bytes.slice(0, cut), bytes.slice(cut)])));
		expect(events).toEqual([{ text: 'čćšžđ' }]);
	});

	it('reads a stream delivered one byte at a time', async () => {
		const text = '{"type":"start"}\n{"type":"delta","text":"Odgovor [1]"}\n{"type":"end"}\n';
		const bytes = new TextEncoder().encode(text);
		const chunks = Array.from(bytes, (byte) => Uint8Array.of(byte));
		const events = await collect(readNdjson(byteStream(chunks)));
		expect(events).toEqual([
			{ type: 'start' },
			{ type: 'delta', text: 'Odgovor [1]' },
			{ type: 'end' }
		]);
	});

	it('yields a final line that has no newline', async () => {
		const bytes = new TextEncoder().encode('{"n":1}\n{"n":2}');
		expect(await collect(readNdjson(byteStream([bytes])))).toEqual([{ n: 1 }, { n: 2 }]);
	});

	it('cancels the stream when the consumer stops early', async () => {
		let cancelled = false;
		const stream = new ReadableStream<Uint8Array>({
			pull(controller) {
				controller.enqueue(new TextEncoder().encode('{"n":1}\n'));
			},
			cancel() {
				cancelled = true;
			}
		});
		for await (const value of readNdjson(stream)) {
			expect(value).toEqual({ n: 1 });
			break;
		}
		expect(cancelled).toBe(true);
	});
});
