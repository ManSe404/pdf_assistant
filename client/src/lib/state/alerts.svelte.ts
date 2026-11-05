// Server errors (5xx, unreachable server) shown as dismissible alerts by the root layout.

export interface AlertItem {
	id: number;
	message: string;
}

const MAX_ALERTS = 3;

class Alerts {
	items = $state<AlertItem[]>([]);
	#nextId = 1;

	push(message: string) {
		// Polling against a dead server would otherwise stack the same alert every 2 s.
		if (this.items.some((item) => item.message === message)) {
			return;
		}
		this.items.push({ id: this.#nextId++, message });
		if (this.items.length > MAX_ALERTS) {
			this.items.shift();
		}
	}

	dismiss(id: number) {
		this.items = this.items.filter((item) => item.id !== id);
	}
}

export const alerts = new Alerts();
