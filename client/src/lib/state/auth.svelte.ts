// The signed-in user. The session itself is an httpOnly cookie the client never sees.

import { api } from '../api/client.ts';
import type { User } from '../api/types.ts';

class Auth {
	user = $state<User | null>(null);
	#known = false;
	#pending: Promise<User | null> | null = null;

	/** Asks the server who is signed in, once; later calls return the cached answer. */
	load(fetch?: typeof globalThis.fetch): Promise<User | null> {
		if (this.#known) {
			return Promise.resolve(this.user);
		}
		this.#pending ??= api
			.get<User | null>('/auth/user', { fetch })
			.then((user) => {
				this.user = user ?? null;
				this.#known = true;
				return this.user;
			})
			// Server unreachable: treat as signed out for now and ask again next time.
			.catch(() => null)
			.finally(() => {
				this.#pending = null;
			});
		return this.#pending;
	}

	async signIn(email: string, password: string) {
		this.#set(await api.post<User>('/auth/signin', { email, password }));
	}

	async signUp(email: string, password: string) {
		this.#set(await api.post<User>('/auth/signup', { email, password }));
	}

	async signOut() {
		await api.post('/auth/signout');
		this.forget();
	}

	/** The session is gone (signed out or a 401): drop the user without asking the server. */
	forget() {
		this.#set(null);
	}

	#set(user: User | null) {
		this.user = user;
		this.#known = true;
	}
}

export const auth = new Auth();
