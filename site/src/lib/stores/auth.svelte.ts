import * as api from '$lib/api';
import type { User, UserRole } from '$lib/types';
import { offline } from './offline.svelte';

const ROLE_RANK: Record<UserRole, number> = { reader: 0, editor: 1, admin: 2 };

class AuthState {
	user = $state<User | null>(null);
	loading = $state(true);
	initialized = $state(false);
	#initPromise: Promise<void> | null = null;
	#authRevision = 0;

	get isLoggedIn() {
		return this.user !== null;
	}

	hasRole(minimum: UserRole): boolean {
		if (!this.user || (offline.offline && minimum !== 'reader')) return false;
		return ROLE_RANK[this.user.role] >= ROLE_RANK[minimum];
	}

	async init() {
		if (this.initialized) return;
		// Concurrent callers (e.g. Header and the page itself both mounting at
		// once) must await the same in-flight refresh instead of each kicking
		// off its own and resolving early before the session is loaded.
		if (!this.#initPromise) {
			this.#initPromise = this.refresh().then(() => {
				this.initialized = true;
			});
		}
		await this.#initPromise;
	}

	async refresh() {
		const revision = ++this.#authRevision;
		this.loading = true;
		try {
			const user = await api.getCurrentUser();
			if (revision === this.#authRevision) this.user = user;
		} catch {
			if (revision === this.#authRevision) this.user = null;
		} finally {
			if (revision === this.#authRevision) this.loading = false;
		}
	}

	async login(identifier: string, password: string) {
		this.user = await api.login(identifier, password);
	}

	async logout() {
		await api.logout();
		++this.#authRevision;
		this.user = null;
		this.loading = false;
	}
}

export const auth = new AuthState();
