import type { FavoriteSort, Recipe, RecipeSummary } from '$lib/types';
import { searchRelevance } from './search';
import { OFFLINE_HEADER, offlineUser, type OfflineSnapshot, type OfflineStorage } from './types';

const reply = (body: unknown, status = 200) =>
	new Response(JSON.stringify(body), {
		status,
		headers: { 'Content-Type': 'application/json', [OFFLINE_HEADER]: '1' }
	});

function listRecipes(snapshot: OfflineSnapshot, params: URLSearchParams): Response | null {
	const sort = params.get('sort') ?? 'title';
	const categoryId = params.get('category_id') ? Number(params.get('category_id')) : null;
	const search = params.get('search')?.trim() || null;
	const page = Number(params.get('page') ?? 1);
	const pageSize = Number(params.get('page_size') ?? 20);
	if (sort === 'manual' && categoryId === null) return null;
	const details = new Map<number, Recipe>(snapshot.recipes.map((recipe) => [recipe.id, recipe]));
	const manual = new Map(
		(snapshot.manualOrder[categoryId ?? 0] ?? []).map((id, index) => [id, index])
	);
	const relevanceOf = (item: RecipeSummary) =>
		search
			? searchRelevance(details.get(item.id) as Recipe, snapshot.comments[item.id] ?? [], search)
			: 0;
	const pool = snapshot.summaries.filter(
		(item) => categoryId === null || item.category_id === categoryId
	);
	const hits = pool
		.map((item) => ({ item, relevance: relevanceOf(item) }))
		.filter((hit) => hit.relevance !== null);
	// A stable sort preserves the server's title ordering inside each relevance group.
	const order = (a: RecipeSummary, b: RecipeSummary) =>
		sort === 'newest'
			? a.created_at < b.created_at
				? 1
				: a.created_at > b.created_at
					? -1
					: b.id - a.id
			: sort === 'manual'
				? (manual.get(a.id) ?? Infinity) - (manual.get(b.id) ?? Infinity)
				: 0;
	hits.sort((a, b) => (a.relevance as number) - (b.relevance as number) || order(a.item, b.item));
	const items = hits
		.slice((page - 1) * pageSize, page * pageSize)
		.map(({ item }) =>
			params.get('summary') === 'true' ? item : (details.get(item.id) as Recipe)
		);
	const otherCategories = [];
	if (search && categoryId !== null && hits.length === 0) {
		const counts = new Map<number, number>();
		for (const item of snapshot.summaries)
			if (
				item.category_id !== null &&
				item.category_id !== categoryId &&
				relevanceOf(item) !== null
			)
				counts.set(item.category_id, (counts.get(item.category_id) ?? 0) + 1);
		for (const { id, name } of snapshot.categories) {
			const count = counts.get(id);
			if (count) otherCategories.push({ id, name, count });
		}
	}
	return reply({
		items,
		total: hits.length,
		other_categories: otherCategories,
		page,
		page_size: pageSize
	});
}

export function answerFromSnapshot(snapshot: OfflineSnapshot, url: URL): Response | null {
	const path = url.pathname;
	const params = url.searchParams;
	const part = (pattern: RegExp) => pattern.exec(path);
	if (path === '/api/auth/me') return reply(offlineUser(snapshot.user));
	if (path === '/api/settings') return reply(snapshot.settings);
	if (path === '/api/categories') return reply(snapshot.categories);
	let match = part(/^\/api\/categories\/(\d+)$/);
	if (match) {
		const category = snapshot.categories.find((item) => item.id === Number(match![1]));
		return category ? reply(category) : reply({ detail: 'Category not found.' }, 404);
	}
	if (path === '/api/recipes') return listRecipes(snapshot, params);
	match = part(/^\/api\/recipes\/(\d+)$/);
	if (match) {
		const recipe = snapshot.recipes.find((item) => item.id === Number(match![1]));
		return recipe ? reply(recipe) : reply({ detail: 'Recipe not found.' }, 404);
	}
	match = part(/^\/api\/recipes\/(\d+)\/comments$/);
	if (match) {
		const comments = snapshot.comments[Number(match[1])];
		return comments ? reply(comments) : reply({ detail: 'Recipe not found.' }, 404);
	}
	match = part(/^\/api\/recipes\/(\d+)\/ratings$/);
	if (match) {
		const id = Number(match[1]);
		const ratings = snapshot.ratings?.[id];
		if (ratings) return reply(ratings);
		if (!snapshot.recipes.some((recipe) => recipe.id === id))
			return reply({ detail: 'Recipe not found.' }, 404);
		return reply({ detail: 'Ratings have not been synced.' }, 503);
	}
	if (path.startsWith('/api/favorites')) {
		const owner = params.get('expected_user_id');
		if (owner !== null && Number(owner) !== snapshot.user.id)
			return reply({ detail: 'The signed-in user changed.' }, 409);
		if (path === '/api/favorites/preferences') return reply(snapshot.favoritePreferences);
		if (path !== '/api/favorites') return null;
		const sort = (params.get('sort') ?? snapshot.favoritePreferences.sort) as FavoriteSort;
		return snapshot.favorites[sort] ? reply(snapshot.favorites[sort]) : null;
	}
	match = part(/^\/api\/users\/(\d+)\/view-preferences$/);
	if (match && Number(match[1]) === snapshot.user.id) return reply(snapshot.viewPreferences);
	return null;
}

let loaded: OfflineSnapshot | null = null;

export function clearLoadedSnapshot() {
	loaded = null;
}

// Answers a request that failed for lack of a server connection from the stored
// snapshot. Without a completed sync for an account there is nothing to serve.
export async function serveOffline(
	url: URL,
	storage: OfflineStorage,
	userId: number
): Promise<Response | null> {
	const meta = await storage.readMeta(userId);
	if (meta?.userId !== userId) return null;
	if (url.pathname.startsWith('/media/')) {
		let media = await storage.getMedia(meta.generation, url.pathname);
		if (!media) {
			const latest = await storage.readMeta(userId);
			if (latest?.userId === userId && latest.generation !== meta.generation)
				media = await storage.getMedia(latest.generation, url.pathname);
			const previous = latest?.userId === userId ? latest.previousGeneration : undefined;
			if (!media && previous) media = await storage.getMedia(previous, url.pathname);
		}
		return media ? new Response(media.body, { headers: media.headers }) : null;
	}
	// Use a request-local reference even when another account loads in parallel.
	const snapshot =
		loaded?.user.id === userId && loaded.generation === meta.generation
			? loaded
			: await storage.readSnapshot(userId);
	if (snapshot?.user.id !== userId) return null;
	loaded = snapshot;
	return answerFromSnapshot(snapshot, url);
}
