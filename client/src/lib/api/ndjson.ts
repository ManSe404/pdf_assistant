// Newline-delimited JSON: one JSON value per line. Network chunks do not respect line
// boundaries (nor UTF-8 character boundaries), so text is buffered until a "\n" arrives.

export class NdjsonError extends Error {
	readonly line: string;
	/** The invalid text was an unterminated last line: the stream was cut off. */
	readonly truncated: boolean;

	constructor(line: string, truncated = false) {
		super(truncated ? 'NDJSON odgovor je prekinut.' : 'Neispravan red u NDJSON odgovoru.');
		this.name = 'NdjsonError';
		this.line = line;
		this.truncated = truncated;
	}
}

/** Buffers text chunks and returns the values of the lines completed so far. */
export class NdjsonParser<T = unknown> {
	#buffer = '';

	/** Adds a chunk and returns the values of every line it completed. */
	push(chunk: string): T[] {
		this.#buffer += chunk;
		const newline = this.#buffer.lastIndexOf('\n');
		if (newline === -1) {
			return [];
		}
		const complete = this.#buffer.slice(0, newline);
		this.#buffer = this.#buffer.slice(newline + 1);
		return parseLines<T>(complete.split('\n'), false);
	}

	/**
	 * Call once the input has ended: parses a last line that had no trailing "\n".
	 * If that line is not valid JSON, the stream was cut off mid-line.
	 */
	flush(): T[] {
		const rest = this.#buffer;
		this.#buffer = '';
		return parseLines<T>([rest], true);
	}
}

function parseLines<T>(lines: string[], unterminated: boolean): T[] {
	const values: T[] = [];
	for (const raw of lines) {
		// trim() also drops the "\r" of "\r\n" line endings.
		const line = raw.trim();
		if (!line) {
			continue;
		}
		try {
			values.push(JSON.parse(line) as T);
		} catch {
			throw new NdjsonError(line, unterminated);
		}
	}
	return values;
}

/** Reads a byte stream as NDJSON and yields one value per line. */
export async function* readNdjson<T = unknown>(
	stream: ReadableStream<Uint8Array>
): AsyncGenerator<T, void, undefined> {
	const reader = stream.getReader();
	// `stream: true` keeps a multi-byte character that is split between chunks
	// (č, ć, š, ž, đ) until its remaining bytes arrive.
	const decoder = new TextDecoder();
	const parser = new NdjsonParser<T>();
	let finished = false;
	try {
		for (;;) {
			const { done, value } = await reader.read();
			if (done) {
				break;
			}
			yield* parser.push(decoder.decode(value, { stream: true }));
		}
		yield* parser.push(decoder.decode());
		yield* parser.flush();
		finished = true;
	} finally {
		if (!finished) {
			// The consumer stopped early or a line was invalid: stop the download too.
			await reader.cancel().catch(() => {});
		}
		reader.releaseLock();
	}
}
