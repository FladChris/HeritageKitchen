import { IDBFactory } from 'fake-indexeddb';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth.svelte';
import { offline } from '$lib/stores/offline.svelte';
import { deviceSession, idbStorage, sessionStorage } from '$lib/offline/idb-storage';
import type { OfflineSnapshot } from '$lib/offline/types';

const prefix = 'heritagekitchen-offline-media-';
const path = '/media/lena.jpg';
const lena = {
	generation: '7-lena',
	syncedAt: '2026-11-22',
	user: { id: 7 },
	recipes: [{ title: 'Lenas Brot' }],
	comments: { 1: [{ content: 'Lenas Kommentar' }] },
	favorites: { manual: [{ recipe_id: 1 }] },
	manualOrder: { 3: [3, 1] }
} as unknown as OfflineSnapshot;
const tim = {
	...lena,
	generation: '8-tim',
	user: { id: 8 },
	favorites: { manual: [{ recipe_id: 2 }] },
	manualOrder: { 3: [2, 1] }
} as OfflineSnapshot;

const shell = 'heritagekitchen-shell-test';
let entries: Map<string, Map<string, Response>>;

beforeEach(() => {
	entries = new Map([[shell, new Map()]]);
	vi.stubGlobal('indexedDB', new IDBFactory());
	vi.stubGlobal('caches', {
		keys: async () => [...entries.keys()],
		delete: async (name: string) => entries.delete(name),
		match: async (request: Request, { cacheName }: CacheQueryOptions & { cacheName: string }) =>
			entries.get(cacheName)?.get(request.url),
		open: async (name: string) => {
			if (!entries.has(name)) entries.set(name, new Map());
			const cache = entries.get(name)!;
			return {
				put: async (request: Request, response: Response) => cache.set(request.url, response)
			};
		}
	});
});

afterEach(() => vi.unstubAllGlobals());

async function seedLena() {
	await deviceSession.confirm(lena.user.id, true, await deviceSession.epoch());
	const epoch = await deviceSession.epoch();
	const storage = sessionStorage(epoch);
	await storage.putMedia(lena.generation, path, new Response('Lenas Bild'));
	await storage.commit(lena);
	return { epoch, storage };
}

it('purges the whole collection and all image generations on device logout, preserving the app shell', async () => {
	const { storage, epoch } = await seedLena();
	await storage.putMedia('7-staging', path, new Response('Zwischenstand'));
	entries.set(prefix + '12-before-upgrade', new Map());
	await deviceSession.revoke({ logout: true });
	expect(await idbStorage.readSnapshot(lena.user.id)).toBeNull();
	expect(await idbStorage.readMeta(lena.user.id)).toBeNull();
	expect(await idbStorage.readStatus(lena.user.id)).toBeNull();
	expect(await idbStorage.getMedia(lena.generation, path)).toBeNull();
	expect([...entries.keys()]).toEqual([shell]);

	await deviceSession.confirm(lena.user.id, true, epoch);
	await deviceSession.confirm(lena.user.id, true, await deviceSession.epoch());
	expect(await deviceSession.binding()).toMatchObject({ pendingLogout: true });
	expect((await deviceSession.binding())?.userId).toBeUndefined();
	await expect(storage.commit(lena)).rejects.toBeDefined();
	await expect(storage.putMedia('7-stale', path, new Response('Bild'))).rejects.toThrow();
	expect([...entries.keys()]).toEqual([shell]);
});

it('retains the current account on revalidation and clears its snapshot before binding a different account', async () => {
	const { epoch } = await seedLena();
	await deviceSession.confirm(lena.user.id, true, epoch);
	expect(await idbStorage.readSnapshot(lena.user.id)).toEqual(lena);
	await deviceSession.confirm(tim.user.id, true, epoch);
	expect(await idbStorage.readSnapshot(lena.user.id)).toBeNull();
	expect([...entries.keys()]).toEqual([shell]);

	const binding = await deviceSession.binding();
	expect(binding).toMatchObject({ userId: tim.user.id, purging: false });
	await sessionStorage(binding!.epoch).commit(tim);
	expect(await idbStorage.readSnapshot(tim.user.id)).toEqual(tim);

	// A delayed rejection from Lena's old session can't erase Tim's new collection.
	await deviceSession.revoke({ epoch });
	expect(await idbStorage.readSnapshot(tim.user.id)).toEqual(tim);
});

it('retries interrupted image cleanup before restoring an offline binding', async () => {
	await seedLena();
	const remove = vi.spyOn(caches, 'delete').mockRejectedValueOnce(new Error('storage unavailable'));
	await expect(deviceSession.revoke({ logout: true })).rejects.toThrow('storage unavailable');
	const epoch = await deviceSession.epoch();
	expect(await deviceSession.binding()).toMatchObject({ purging: true });
	expect(await idbStorage.readSnapshot(lena.user.id)).toBeNull();
	await deviceSession.resumePurge();
	expect(await deviceSession.binding()).toMatchObject({
		epoch,
		pendingLogout: true,
		purging: false
	});
	await deviceSession.resumePurge();
	expect(remove).toHaveBeenCalledTimes(2);
	expect([...entries.keys()]).toEqual([shell]);
});

it('allows explicit app logout while offline and drops the old in-memory identity', async () => {
	await seedLena();
	const previousUser = auth.user;
	auth.user = lena.user;
	offline.markConnection(true);
	const fetcher = vi.fn().mockRejectedValue(new TypeError('Offline'));
	vi.stubGlobal('fetch', fetcher);
	const postMessage = vi.fn();
	vi.stubGlobal(
		'BroadcastChannel',
		class {
			postMessage = postMessage;
		}
	);
	try {
		await auth.logout();
		expect(auth.user).toBeNull();
		expect(await idbStorage.readSnapshot(lena.user.id)).toBeNull();
		expect(await deviceSession.binding()).toMatchObject({ pendingLogout: true });
		expect(postMessage).toHaveBeenCalledWith('offline-data-wiped');
		expect(fetcher).toHaveBeenCalledWith(
			'/api/auth/logout',
			expect.objectContaining({ method: 'POST' })
		);
	} finally {
		auth.user = previousUser;
		offline.markConnection(false);
	}
});
