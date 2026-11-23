import { fromStore } from 'svelte/store';
import { offlineConnection } from '$lib/offline/connection';
import { mayWorkOffline, syncOffline } from '$lib/offline/sync';
import {
	deviceSession,
	idbStorage,
	offlineStorageAvailable,
	sessionStorage,
	withSyncLock
} from '$lib/offline/idb-storage';
import { installedApp } from '$lib/offline/installed';
import { SYNC_HEADER, type OfflineStorage } from '$lib/offline/types';
import type { User } from '$lib/types';

// Re-sync at most this often while the app stays open and online.
const RESYNC_AFTER_MS = 15 * 60 * 1000;
const connection = fromStore(offlineConnection);

class OfflineState {
	// True while the server cannot be reached; derived from real responses,
	// not only navigator.onLine, because a missing VPN keeps the browser "online".
	get offline() {
		return connection.current;
	}
	set offline(value: boolean) {
		offlineConnection.set(value);
	}
	incomplete = $state(false);
	syncing = $state(false);
	syncError = $state<string | null>(null);
	generation = $state<string | null>(null);
	lastCompleteSync = $state<{ userId: number; syncedAt: string } | null>(null);
	statusUserId = $state<number | null>(null);
	#attemptedAt = 0;
	#account: number | null = null;
	#probing = false;
	#statusRequest = 0;

	constructor() {
		offlineConnection.subscribe((offline) => {
			if (offline) this.#attemptedAt = 0;
		});
	}

	get storage(): OfflineStorage | null {
		return offlineStorageAvailable() ? idbStorage : null;
	}

	markConnection(offline: boolean) {
		offlineConnection.set(offline);
	}

	async probe(account: () => User | null) {
		if (!installedApp() || this.#probing) return;
		this.#probing = true;
		try {
			const response = await fetch('/api/auth/me', {
				credentials: 'include',
				cache: 'no-store',
				headers: { [SYNC_HEADER]: '1', 'X-Offline-Read': '1' },
				signal: AbortSignal.timeout(8000)
			});
			this.markConnection(false);
			if (response.ok) {
				const user: User = await response.json();
				if (account()?.id === user.id) void this.sync(user);
			}
		} catch {
			this.markConnection(true);
		} finally {
			this.#probing = false;
			void this.loadStatus(account());
		}
	}

	// First sync not finished: there is no complete copy to read from.
	async loadStatus(user: User | null, cleanup = false) {
		const request = ++this.#statusRequest;
		const storage = this.storage;
		const eligible = mayWorkOffline(user);
		if (!storage || !eligible) {
			this.incomplete = eligible;
			this.generation = null;
			this.lastCompleteSync = null;
			this.syncError = eligible ? 'Der Offline-Speicher ist nicht verfügbar.' : null;
			this.statusUserId = eligible ? user.id : null;
			return;
		}
		const userId = user.id;
		if (cleanup)
			void withSyncLock(async (lease) => {
				const binding = await deviceSession.binding();
				if (!binding?.purging && binding?.userId === userId)
					await sessionStorage(binding.epoch).pruneMedia(userId, true, lease);
			}).catch(() => undefined);
		try {
			const [status, meta] = await Promise.all([
				storage.readStatus(userId),
				storage.readMeta(userId)
			]);
			if (this.syncing || request !== this.#statusRequest) return;
			const unfinished = status !== null && status.state !== 'complete';
			this.incomplete = !meta;
			this.generation = meta?.generation ?? null;
			this.lastCompleteSync = meta ? { userId, syncedAt: meta.syncedAt } : null;
			this.syncError = unfinished
				? (status.error ?? 'Der letzte Offline-Abgleich wurde unterbrochen.')
				: null;
			// With no saved status or snapshot, the first attempt is still pending.
			this.statusUserId = status || meta ? userId : null;
		} catch {
			if (this.syncing || request !== this.#statusRequest) return;
			this.incomplete = this.lastCompleteSync?.userId !== userId;
			this.syncError = 'Der Offline-Stand konnte nicht gelesen werden.';
			this.statusUserId = userId;
		}
	}

	async sync(user: User) {
		const storage = this.storage;
		if (!installedApp() || this.syncing || this.offline || !mayWorkOffline(user)) return;
		if (this.#account === user.id && Date.now() - this.#attemptedAt < RESYNC_AFTER_MS) return;
		this.#account = user.id;
		this.#attemptedAt = Date.now();
		if (!storage) {
			this.incomplete = true;
			this.lastCompleteSync = null;
			this.syncError = 'Der Offline-Speicher ist nicht verfügbar.';
			this.statusUserId = user.id;
			return;
		}
		this.syncing = true;
		try {
			const previous = await storage.readMeta(user.id).catch(() => null);
			this.incomplete = !previous;
			this.lastCompleteSync = previous ? { userId: user.id, syncedAt: previous.syncedAt } : null;
			const result = await withSyncLock(async (lease) => {
				const binding = await deviceSession.binding();
				if (binding?.purging || binding?.userId !== user.id) return;
				return syncOffline({ storage: sessionStorage(binding.epoch), user, lease });
			});
			if (!result) {
				this.#attemptedAt = 0;
				return;
			}
			if (result.ok) {
				this.generation = result.snapshot.generation;
				this.lastCompleteSync = { userId: user.id, syncedAt: result.snapshot.syncedAt };
			}
			this.syncError = result.ok ? null : result.error;
			this.statusUserId = user.id;
			this.incomplete = !result.ok && !(await storage.readMeta(user.id).catch(() => null));
		} catch {
			this.syncError = 'Der Offline-Abgleich konnte nicht abgeschlossen werden.';
			this.statusUserId = user.id;
		} finally {
			this.syncing = false;
		}
	}
}

export const offline = new OfflineState();
