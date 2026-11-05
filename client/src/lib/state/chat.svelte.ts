// Conversations about one PDF: choosing, creating and deleting them, streaming answers
// and voting. One instance per document page.

import { SvelteSet } from 'svelte/reactivity';
import { api, isAbortError, send } from '../api/client.ts';
import { inlineError, isAlerted, messageOf } from '../api/errors.ts';
import { NdjsonError, readNdjson } from '../api/ndjson.ts';
import type { Conversation, Message, StreamEvent, Vote } from '../api/types.ts';

const INTERRUPTED = 'Veza je prekinuta pre kraja odgovora.';

/** The answer currently streaming, or the last one that failed (never saved). */
export interface PendingAnswer {
	conversationId: string;
	text: string;
	error: string | null;
}

let localIds = 0;

export class ChatSession {
	readonly pdfId: string;

	conversations = $state<Conversation[]>([]);
	activeId = $state<string | null>(null);
	loading = $state(true);
	loadError = $state('');
	/** Creating or deleting a conversation. */
	busy = $state(false);
	streaming = $state(false);
	pending = $state<PendingAnswer | null>(null);
	/** Text of the question box; restored when a question could not be sent. */
	draft = $state('');
	/** A problem to show above the question box (not a streamed error). */
	notice = $state('');
	/** Messages with a vote request in flight. */
	voting = new SvelteSet<string>();

	active = $derived(this.conversations.find((c) => c.id === this.activeId) ?? null);

	#abort: AbortController | null = null;

	constructor(pdfId: string) {
		this.pdfId = pdfId;
	}

	async load() {
		this.loading = true;
		this.loadError = '';
		try {
			this.conversations = await api.get<Conversation[]>(`/pdfs/${this.pdfId}/conversations`);
			if (!this.active) {
				this.activeId = this.conversations[0]?.id ?? null;
			}
		} catch (error) {
			this.loadError = messageOf(error);
		} finally {
			this.loading = false;
		}
	}

	select(id: string) {
		if (this.streaming || id === this.activeId) {
			return;
		}
		this.activeId = id;
		this.pending = null;
		this.notice = '';
	}

	async create(): Promise<Conversation | null> {
		this.busy = true;
		this.notice = '';
		try {
			const created = await api.post<Conversation>(`/pdfs/${this.pdfId}/conversations`);
			this.conversations = [created, ...this.conversations];
			this.activeId = created.id;
			this.pending = null;
			// Return the reactive proxy, not the plain object, so later mutations show up.
			return this.conversations[0];
		} catch (error) {
			this.notice = inlineError(error);
			return null;
		} finally {
			this.busy = false;
		}
	}

	async remove(id: string) {
		this.busy = true;
		this.notice = '';
		try {
			await api.delete(`/conversations/${id}`);
			this.conversations = this.conversations.filter((c) => c.id !== id);
			if (this.activeId === id) {
				this.activeId = this.conversations[0]?.id ?? null;
				this.pending = null;
			}
		} catch (error) {
			this.notice = inlineError(error);
		} finally {
			this.busy = false;
		}
	}

	/**
	 * Sends a question and streams the answer into `pending`. Creates a conversation
	 * first when there is none. Returns false when the question was not sent.
	 */
	async send(question: string): Promise<boolean> {
		const content = question.trim();
		if (!content || this.streaming || this.busy) {
			return false;
		}

		this.notice = '';
		this.pending = null;
		const conversation = this.active ?? (await this.create());
		if (!conversation) {
			return false;
		}

		const controller = new AbortController();
		this.#abort = controller;
		this.streaming = true;
		this.draft = '';

		const localId = `local-${++localIds}`;
		conversation.messages.push({
			id: localId,
			role: 'user',
			content,
			// Replaced by the saved message as soon as the stream starts.
			// eslint-disable-next-line svelte/prefer-svelte-reactivity -- a timestamp, not state
			created_at: new Date().toISOString(),
			sources: [],
			vote: null
		});
		this.pending = { conversationId: conversation.id, text: '', error: null };
		let started = false;
		let finished = false;

		try {
			const response = await send('POST', `/conversations/${conversation.id}/messages`, {
				body: { content },
				signal: controller.signal
			});
			if (!response.body) {
				throw new NdjsonError('');
			}
			for await (const event of readNdjson<StreamEvent>(response.body)) {
				// Read through `this.pending`, the reactive proxy, so the UI updates.
				const current = this.pending;
				if (event.type === 'start') {
					started = true;
					replaceMessage(conversation, localId, event.user_message);
					// The server names a conversation after its first question.
					conversation.title = event.title;
				} else if (event.type === 'delta' && current) {
					current.text += event.text;
				} else if (event.type === 'end') {
					finished = true;
					conversation.messages.push(event.message);
					this.pending = null;
				} else if (event.type === 'error' && current) {
					finished = true;
					current.error = event.detail || 'Odgovor nije završen.';
				}
			}
			if (!finished && this.pending) {
				this.pending.error = INTERRUPTED;
			}
		} catch (error) {
			if (isAbortError(error)) {
				return false;
			}
			if (!started) {
				// Nothing was saved: take the question back so it can be sent again.
				conversation.messages = conversation.messages.filter((m) => m.id !== localId);
				this.pending = null;
				this.draft = content;
				this.notice = isAlerted(error) ? '' : streamFailure(error);
				return false;
			}
			if (this.pending) {
				this.pending.error = streamFailure(error);
			}
		} finally {
			this.streaming = false;
			if (this.#abort === controller) {
				this.#abort = null;
			}
		}

		return started;
	}

	/** Thumbs up or down; clicking the active thumb again (score 0) removes the vote. */
	async vote(message: Message, vote: Vote) {
		if (this.voting.has(message.id)) {
			return;
		}
		const score = message.vote === vote ? 0 : vote;
		const previous = message.vote;
		message.vote = score === 0 ? null : score;
		this.voting.add(message.id);
		try {
			const saved = await api.put<Message>(`/messages/${message.id}/vote`, { score });
			message.vote = saved.vote;
		} catch (error) {
			message.vote = previous;
			this.notice = inlineError(error);
		} finally {
			this.voting.delete(message.id);
		}
	}

	/** Stops a running stream, for example when the page is left. */
	dispose() {
		this.#abort?.abort();
	}
}

function streamFailure(error: unknown): string {
	if (error instanceof NdjsonError) {
		return error.truncated ? INTERRUPTED : 'Server je poslao neispravan odgovor.';
	}
	// Reading the body fails with a TypeError when the connection drops.
	if (error instanceof TypeError) {
		return INTERRUPTED;
	}
	return messageOf(error);
}

function replaceMessage(conversation: Conversation, id: string, message: Message) {
	const index = conversation.messages.findIndex((m) => m.id === id);
	if (index === -1) {
		conversation.messages.push(message);
	} else {
		conversation.messages[index] = message;
	}
}
