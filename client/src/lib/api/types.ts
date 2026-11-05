// Shapes of the backend HTTP API (see the API contract). All ids are UUID strings,
// all times ISO 8601 strings in UTC.

export interface User {
	id: string;
	email: string;
}

export type PdfStatus = 'processing' | 'ready' | 'failed';

export interface Pdf {
	id: string;
	name: string;
	status: PdfStatus;
	/** Set when `status` is `failed`; Serbian, meant for the user. */
	error: string | null;
	pages: number | null;
	chunks: number | null;
	size_bytes: number;
	created_at: string;
}

export interface Component {
	name: string;
	label: string;
}

export interface Components {
	llm: Component;
	retriever: Component;
	memory: Component;
}

export type ComponentType = keyof Components;

export interface Source {
	/** Matches the `[n]` in the answer. */
	n: number;
	/** 1-based page number. */
	page: number;
	text: string;
}

export type Vote = 1 | -1;

export interface Message {
	id: string;
	role: 'user' | 'assistant';
	/** Assistant content is Markdown and cites sources as [1], [2]. */
	content: string;
	created_at: string;
	sources: Source[];
	vote: Vote | null;
}

export interface Conversation {
	id: string;
	pdf_id: string;
	title: string;
	created_at: string;
	components: Components;
	/** Oldest first. */
	messages: Message[];
}

/** One line of the NDJSON answer stream. */
export type StreamEvent =
	| { type: 'start'; user_message: Message; title: string }
	| { type: 'delta'; text: string }
	| { type: 'end'; message: Message }
	| { type: 'error'; detail: string };

export interface ComponentScore {
	name: string;
	label: string;
	/** Still configured; inactive ones only appear because they have votes. */
	active: boolean;
	up: number;
	down: number;
	/** up / (up + down), null without votes. */
	satisfaction: number | null;
	/** Chance (0..1) that a new conversation picks it; 0 when inactive. */
	weight: number;
}

export type Scores = Record<ComponentType, ComponentScore[]>;
