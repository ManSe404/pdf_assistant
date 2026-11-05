// The signed-in user's PDFs, newest first.

import { api } from '../api/client.ts';
import { messageOf } from '../api/errors.ts';
import type { Pdf } from '../api/types.ts';

class Documents {
	items = $state<Pdf[]>([]);
	loaded = $state(false);
	error = $state('');
	/** True while any PDF is still being indexed; the list polls meanwhile. */
	processing = $derived(this.items.some((pdf) => pdf.status === 'processing'));
	#inFlight = false;

	async refresh() {
		// A slow response must not pile up requests from the 2 s poll.
		if (this.#inFlight) {
			return;
		}
		this.#inFlight = true;
		try {
			this.items = await api.get<Pdf[]>('/pdfs');
			this.error = '';
		} catch (error) {
			this.error = messageOf(error);
		} finally {
			this.#inFlight = false;
			this.loaded = true;
		}
	}

	/** Adds a freshly uploaded PDF so the list shows it before the next refresh. */
	add(pdf: Pdf) {
		this.items = [pdf, ...this.items.filter((item) => item.id !== pdf.id)];
	}

	async remove(id: string) {
		await api.delete(`/pdfs/${id}`);
		this.items = this.items.filter((pdf) => pdf.id !== id);
	}

	/** Clears the list on sign-out so the next user does not see it. */
	reset() {
		this.items = [];
		this.loaded = false;
		this.error = '';
	}
}

export const documents = new Documents();
