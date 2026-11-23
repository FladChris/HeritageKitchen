import type {
	Category,
	Favorite,
	FavoritePreferences,
	FavoriteSort,
	Recipe,
	RecipeComment,
	RecipeRatingSummary,
	RecipeList,
	RecipeSummary,
	Settings,
	User,
	ViewPreferences
} from '$lib/types';
import {
	OFFLINE_HEADER,
	SYNC_HEADER,
	offlineUser,
	type OfflineSnapshot,
	type OfflineStorage
} from './types';

export type SyncResult = { ok: true; snapshot: OfflineSnapshot } | { ok: false; error: string };

const PAGE_SIZE = 100;
const CONCURRENCY = 4;
const FAVORITE_SORTS: FavoriteSort[] = ['recent', 'name', 'manual'];

// Only active, approved accounts may keep recipe data on the device.
export function mayWorkOffline(user: User | null): user is User {
	return user !== null && user.is_active && !user.pending_approval;
}

async function mapLimited<T, R>(items: T[], work: (item: T) => Promise<R>): Promise<R[]> {
	const results: R[] = new Array(items.length);
	let next = 0;
	let failed = false;
	const settled = await Promise.allSettled(
		Array.from({ length: Math.min(CONCURRENCY, items.length) }, async () => {
			while (!failed && next < items.length) {
				const index = next++;
				try {
					results[index] = await work(items[index]);
				} catch (error) {
					failed = true;
					throw error;
				}
			}
		})
	);
	for (const result of settled) if (result.status === 'rejected') throw result.reason;
	return results;
}

export async function syncOffline(options: {
	storage: OfflineStorage;
	user: User;
	fetcher?: typeof fetch;
	now?: () => Date;
	lease?: string;
}): Promise<SyncResult> {
	const { storage, user } = options;
	const fetcher = options.fetcher ?? fetch;
	const now = options.now ?? (() => new Date());
	const generation = `${user.id}-${crypto.randomUUID()}`;
	if (!mayWorkOffline(user))
		return { ok: false, error: 'Dieses Konto ist nicht für den Offline-Abgleich freigeschaltet.' };
	try {
		// The sync header keeps the service worker from answering with stored data
		// when the connection drops: stored data must never be synced as fresh data.
		const get = async <T>(path: string): Promise<T> => {
			const response = await fetcher(path, {
				credentials: 'include',
				cache: 'no-store',
				signal: AbortSignal.timeout(30000),
				headers: { [SYNC_HEADER]: '1' }
			});
			if (!response.ok || response.headers.get(OFFLINE_HEADER))
				throw new Error(`Abruf fehlgeschlagen (${path}: ${response.status})`);
			return (await response.json()) as T;
		};
		const listAll = async <T extends RecipeSummary>(query: string): Promise<T[]> => {
			const items: T[] = [];
			const ids = new Set<number>();
			let total: number | undefined;
			for (let page = 1; ; page++) {
				const result = await get<Omit<RecipeList, 'items'> & { items: T[] }>(
					`/api/recipes?${query}&page=${page}&page_size=${PAGE_SIZE}`
				);
				total ??= result.total;
				for (const item of result.items) ids.add(item.id);
				items.push(...result.items);
				if (
					result.total !== total ||
					items.length !== ids.size ||
					items.length > total ||
					(!result.items.length && items.length < total)
				)
					throw new Error('Die Rezeptliste änderte sich während des Abgleichs.');
				if (items.length === total) return items;
			}
		};

		const me = await get<User>('/api/auth/me');
		if (me.id !== user.id || !mayWorkOffline(me))
			throw new Error('Die Anmeldung gilt nicht mehr für den Offline-Abgleich.');
		await storage.writeStatus({ userId: user.id, state: 'pending', at: now().toISOString() });
		const settings = await get<Settings>('/api/settings');
		const categories = await get<Category[]>('/api/categories');
		const summaries = await listAll('summary=true&sort=title');
		const recipes = await listAll<Recipe>('summary=false&sort=title');
		const details = new Map(recipes.map((recipe) => [recipe.id, recipe]));
		if (
			details.size !== summaries.length ||
			summaries.some((summary) => {
				const recipe = details.get(summary.id);
				return (
					!recipe || recipe.version !== summary.version || recipe.updated_at !== summary.updated_at
				);
			})
		)
			throw new Error('Die Rezeptliste änderte sich während des Abgleichs.');

		const socialData = await mapLimited(recipes, async (recipe) => {
			const path = `/api/recipes/${recipe.id}`;
			const comments = await get<RecipeComment[]>(`${path}/comments`);
			const ratings = await get<RecipeRatingSummary>(`${path}/ratings`);
			const checked = await get<Recipe>(path);
			if (checked.version !== recipe.version || checked.updated_at !== recipe.updated_at)
				throw new Error('Ein Rezept änderte sich während des Abgleichs.');
			return { comments, ratings };
		});
		const comments = Object.fromEntries(
			recipes.map((recipe, index) => [recipe.id, socialData[index].comments])
		);
		const ratings = Object.fromEntries(
			recipes.map((recipe, index) => [recipe.id, socialData[index].ratings])
		);
		const owner = `expected_user_id=${user.id}`;
		const favorites = {} as Record<FavoriteSort, Favorite[]>;
		for (const sort of FAVORITE_SORTS)
			favorites[sort] = await get<Favorite[]>(`/api/favorites?sort=${sort}&${owner}`);
		const favoritePreferences = await get<FavoritePreferences>(
			`/api/favorites/preferences?${owner}`
		);
		const viewPreferences = await get<ViewPreferences>(`/api/users/${user.id}/view-preferences`);
		const manualOrder: Record<number, number[]> = {};
		for (const category of categories)
			manualOrder[category.id] = (
				await listAll(`summary=true&sort=manual&category_id=${category.id}`)
			).map((recipe) => recipe.id);

		const previous = await storage.readMeta(user.id);
		const mediaPaths = [
			...new Set(
				[
					...recipes.flatMap((recipe) => recipe.images.map((image) => image.file_path)),
					...categories.map((category) => category.image_path),
					me.profile_image_path
				].filter((path): path is string => !!path)
			)
		];
		// Image URLs are immutable. Reuse cached responses to save network bandwidth.
		// The staging cache needs room alongside the live cache until the new snapshot commits.
		await storage.pruneMedia(user.id, false, options.lease);
		await mapLimited(mediaPaths, async (path) => {
			if (
				previous &&
				previous.userId === user.id &&
				(await storage.copyMedia(previous.generation, generation, path))
			)
				return;
			const response = await fetcher(path, {
				credentials: 'include',
				cache: 'no-store',
				signal: AbortSignal.timeout(60000),
				headers: { [SYNC_HEADER]: '1' }
			});
			if (
				!response.ok ||
				response.headers.get(OFFLINE_HEADER) ||
				!response.headers.get('Content-Type')?.startsWith('image/')
			)
				throw new Error(`Bild konnte nicht geladen werden (${path}: ${response.status})`);
			await storage.putMedia(generation, path, response);
		});

		const current = await get<User>('/api/auth/me');
		if (current.id !== user.id || !mayWorkOffline(current))
			throw new Error('Die Anmeldung gilt nicht mehr für den Offline-Abgleich.');
		const snapshot: OfflineSnapshot = {
			generation,
			syncedAt: now().toISOString(),
			user: offlineUser(me),
			settings,
			categories,
			summaries,
			recipes,
			comments,
			ratings,
			favorites,
			favoritePreferences,
			viewPreferences,
			manualOrder
		};
		await storage.commit(snapshot, options.lease);
		return { ok: true, snapshot };
	} catch (error) {
		await storage.discardMedia(generation).catch(() => undefined);
		const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
		await storage
			.writeStatus({ userId: user.id, state: 'failed', at: now().toISOString(), error: message })
			.catch(() => undefined);
		return { ok: false, error: message };
	}
}
