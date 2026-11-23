import type { OfflineMeta, OfflineSnapshot, OfflineStatus, OfflineStorage } from './types';

// Account records live in IndexedDB and image bodies in Cache Storage.
const DB_NAME = 'heritagekitchen-offline';
const STORE = 'kv';
const MEDIA_PREFIX = 'heritagekitchen-offline-media-';
const SYNC_LEASE = 'sync-lease';
const DEVICE_SESSION = 'offline-device-session';
type DeviceBinding = {
	epoch: string;
	userId?: number;
	purging?: boolean;
	pendingLogout?: boolean;
};

const LEASE_MS = 5 * 60 * 1000;

function open(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(DB_NAME, 1);
		request.onupgradeneeded = () => request.result.createObjectStore(STORE);
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(request.error);
	});
}

async function run<T>(
	mode: IDBTransactionMode,
	work: (store: IDBObjectStore) => IDBRequest | IDBRequest[]
): Promise<T> {
	const db = await open();
	try {
		return await new Promise<T>((resolve, reject) => {
			const transaction = db.transaction(STORE, mode);
			const result = work(transaction.objectStore(STORE));
			const requests = Array.isArray(result) ? result : [result];
			transaction.oncomplete = () => resolve(requests[0]?.result as T);
			transaction.onerror = () => reject(transaction.error);
			transaction.onabort = () =>
				reject(transaction.error ?? new DOMException('Transaction aborted', 'AbortError'));
		});
	} finally {
		db.close();
	}
}

const mediaKey = (path: string) => new Request(new URL(path, 'https://offline.invalid').href);
const read = <T>(key: string) =>
	run<T | undefined>('readonly', (store) => store.get(key)).then((value) => value ?? null);

async function writeForSession(epoch: string | undefined, work: (store: IDBObjectStore) => void) {
	await run('readwrite', (store) => {
		const binding = store.get(DEVICE_SESSION);
		binding.onsuccess = () => {
			if (!epoch || binding.result?.epoch !== epoch || binding.result.purging) {
				store.transaction.abort();
				return;
			}
			work(store);
		};
		return binding;
	});
}

export function sessionStorage(epoch?: string): OfflineStorage {
	async function checkSession() {
		const binding = await deviceSession.binding();
		if (!epoch || binding?.epoch !== epoch || binding.purging)
			throw new Error('Offline device session changed');
	}
	async function saveMedia(generation: string, path: string, response: Response) {
		try {
			await checkSession();
			const cache = await caches.open(MEDIA_PREFIX + generation);
			await checkSession();
			await cache.put(mediaKey(path), response);
			await checkSession();
		} catch (error) {
			await caches.delete(MEDIA_PREFIX + generation);
			throw error;
		}
	}

	return {
		readMeta: (userId) => read<OfflineMeta>(`meta:${userId}`),
		readSnapshot: (userId) => read<OfflineSnapshot>(`snapshot:${userId}`),
		async commit(snapshot, lease) {
			const userId = snapshot.user.id;
			const meta: OfflineMeta = {
				generation: snapshot.generation,
				userId,
				syncedAt: snapshot.syncedAt
			};
			const status: OfflineStatus = { userId, state: 'complete', at: snapshot.syncedAt };
			const key = `meta:${userId}`;
			await writeForSession(epoch, (store) => {
				const guard = store.get(SYNC_LEASE);
				guard.onsuccess = () => {
					if (lease && (guard.result?.owner !== lease || guard.result.until <= Date.now())) {
						store.transaction.abort();
						return;
					}
					const previous = store.get(key);
					previous.onsuccess = () =>
						store.put({ ...meta, previousGeneration: previous.result?.generation }, key);
					store.put(snapshot, `snapshot:${userId}`);
					store.put(status, `status:${userId}`);
				};
			});
		},
		readStatus: (userId) => read<OfflineStatus>(`status:${userId}`),
		async writeStatus(status) {
			await writeForSession(epoch, (store) => store.put(status, `status:${status.userId}`));
		},
		async copyMedia(from, to, path) {
			const cached = await caches.match(mediaKey(path), { cacheName: MEDIA_PREFIX + from });
			if (!cached) return false;
			await saveMedia(to, path, cached);
			return true;
		},
		putMedia: saveMedia,
		async getMedia(generation, path) {
			return (await caches.match(mediaKey(path), { cacheName: MEDIA_PREFIX + generation })) ?? null;
		},
		async discardMedia(generation) {
			await caches.delete(MEDIA_PREFIX + generation);
		},
		async pruneMedia(userId, keepPrevious = false, lease) {
			const meta = await this.readMeta(userId);
			const names = await caches.keys();
			if (lease && !(await updateLease(lease, 'renew'))) throw new Error('Offline sync lock lost');
			await checkSession();
			await Promise.all(
				names
					.filter(
						(name) =>
							name.startsWith(`${MEDIA_PREFIX}${userId}-`) &&
							name !== MEDIA_PREFIX + meta?.generation &&
							(!keepPrevious || name !== MEDIA_PREFIX + meta?.previousGeneration)
					)
					.map((name) => caches.delete(name))
			);
		}
	};
}

export const idbStorage = sessionStorage();

export function offlineStorageAvailable(): boolean {
	return typeof indexedDB !== 'undefined' && typeof caches !== 'undefined';
}
const readBinding = () => read<DeviceBinding>(DEVICE_SESSION);

async function changeBinding(
	next: (current: DeviceBinding | null) => Omit<DeviceBinding, 'epoch' | 'purging'> | undefined
) {
	let replacement: DeviceBinding | undefined;
	let removedAccount = false;
	await run('readwrite', (store) => {
		const request = store.get(DEVICE_SESSION);
		request.onsuccess = () => {
			const current = request.result ?? null;
			const update = next(current);
			if (!update) return;
			removedAccount = current?.userId !== undefined;
			replacement = { ...update, epoch: crypto.randomUUID(), purging: true };
			store.clear();
			store.put(replacement, DEVICE_SESSION);
		};
		return request;
	});
	if (!replacement) return false;

	await finishPurge(replacement.epoch);
	return removedAccount;
}

async function finishPurge(epoch: string) {
	// Only delete names captured while this epoch barred new image writes.
	const names = (await caches.keys()).filter((name) => name.startsWith(MEDIA_PREFIX));
	const binding = await readBinding();
	if (binding?.epoch !== epoch || !binding.purging) return;
	await Promise.all(names.map((name) => caches.delete(name)));
	await run('readwrite', (store) => {
		const request = store.get(DEVICE_SESSION);
		request.onsuccess = () => {
			if (request.result?.epoch === epoch && request.result.purging)
				store.put({ ...request.result, purging: false }, DEVICE_SESSION);
		};
		return request;
	});
}

export const deviceSession = {
	binding: readBinding,
	async resumePurge() {
		const binding = await readBinding();
		if (binding?.purging) await finishPurge(binding.epoch);
	},
	async epoch() {
		return (await readBinding())?.epoch ?? '';
	},
	confirm(userId: number, mayBind: boolean, epoch: string) {
		return changeBinding((current) => {
			if ((current?.epoch ?? '') !== epoch || current?.pendingLogout) return;
			if (!current?.purging && current?.userId === userId) return;
			if (!current?.purging && current?.userId === undefined && !mayBind) return;
			return { userId: mayBind ? userId : undefined };
		});
	},
	revoke({ epoch, logout }: { epoch?: string; logout?: boolean } = {}) {
		return changeBinding((current) => {
			if (epoch !== undefined && (current?.epoch ?? '') !== epoch) return;
			if (current && !current.purging && current.userId === undefined && !logout) return;
			return { pendingLogout: logout || current?.pendingLogout };
		});
	},
	async finishLogout(epoch: string) {
		await run('readwrite', (store) => {
			const request = store.get(DEVICE_SESSION);
			request.onsuccess = () => {
				if (request.result?.epoch === epoch)
					store.put({ ...request.result, pendingLogout: false }, DEVICE_SESSION);
			};
			return request;
		});
	}
};

async function updateLease(owner: string, action: 'acquire' | 'renew' | 'release') {
	let acquired = false;
	await run('readwrite', (store) => {
		const request = store.get(SYNC_LEASE);
		request.onsuccess = () => {
			const lease = request.result;
			const now = Date.now();
			if (action === 'acquire' ? lease?.until > now : lease?.owner !== owner) return;
			if (action === 'release') store.delete(SYNC_LEASE);
			else store.put({ owner, until: now + LEASE_MS }, SYNC_LEASE);
			acquired = true;
		};
		return request;
	});
	return acquired;
}

export async function withSyncLock<T>(
	work: (lease?: string) => Promise<T>
): Promise<T | undefined> {
	if (navigator.locks) {
		return navigator.locks.request('heritagekitchen-offline-sync', { ifAvailable: true }, (lock) =>
			lock ? work() : undefined
		);
	}
	const owner = crypto.randomUUID();
	if (!(await updateLease(owner, 'acquire'))) return;
	const heartbeat = setInterval(
		() => void updateLease(owner, 'renew').catch(() => undefined),
		LEASE_MS / 4
	);
	try {
		return await work(owner);
	} finally {
		clearInterval(heartbeat);
		await updateLease(owner, 'release').catch(() => undefined);
	}
}
