import { createHash } from 'node:crypto';
import { foldText, searchRelevance } from '$lib/offline/search';
import { expect, it, vi } from 'vitest';
import { answerFromSnapshot, serveOffline } from '$lib/offline/serve';
import { syncOffline, mayWorkOffline } from '$lib/offline/sync';
import type { OfflineSnapshot, OfflineStorage } from '$lib/offline/types';
import type { Recipe, User } from '$lib/types';

const ratings = {
	average: 4.5,
	count: 1,
	ratings: [{ username: 'Lena', stars: 4.5 }]
};
const user: User = {
	id: 7,
	username: 'lena',
	email: null,
	email_verified_at: null,
	role: 'reader',
	is_active: true,
	pending_approval: false,
	created_at: ''
};
const recipe = (id: number, title = 'Suppe', category_id = 1): Recipe =>
	({
		id,
		title,
		category_id,
		version: 1,
		created_at: '2026-01-01',
		updated_at: '2026-01-01',
		steps: [],
		ingredient_groups: [],
		ingredients: [],
		images: [{ id, file_path: '/media/recipe-images/' + id + '.jpg' }]
	}) as Recipe;
const url = (path: string) => new URL(path, 'https://kitchen.test');

function harness(initial: Recipe[] = [recipe(1), recipe(2)]) {
	let snapshot: OfflineSnapshot | null = null;
	let previousGeneration: string | undefined;
	let recipes = initial;
	let fail: string | null = null;
	let quota = false;
	let finalUser = user;
	let authReads = 0;
	let editedDuringRead = false;
	const media = new Map<string, Map<string, Response>>();
	const storage = {
		readSnapshot: async (id?: number) => (id === undefined || id === user.id ? snapshot : null),
		readMeta: async () =>
			snapshot && { generation: snapshot.generation, userId: user.id, previousGeneration },
		commit: vi.fn(async (next: OfflineSnapshot) => {
			previousGeneration = snapshot?.generation;
			snapshot = next;
		}),
		writeStatus: vi.fn(async () => {}),
		copyMedia: async () => false,
		putMedia: async (generation: string, path: string, response: Response) => {
			if (quota) throw new DOMException('Full', 'QuotaExceededError');
			if (!media.has(generation)) media.set(generation, new Map());
			media.get(generation)!.set(path, response);
		},
		getMedia: async (generation: string, path: string) => media.get(generation)?.get(path) ?? null,
		pruneMedia: async () => {
			for (const id of media.keys()) if (id !== snapshot?.generation) media.delete(id);
		},
		discardMedia: async (generation: string) => {
			media.delete(generation);
		}
	} as unknown as OfflineStorage;
	const fetcher = vi.fn(async (input: string) => {
		const { pathname, searchParams } = url(input);
		if (pathname === fail) throw new TypeError('Network unavailable');
		if (pathname === '/api/auth/me') return Response.json(++authReads % 2 ? user : finalUser);
		if (pathname === '/api/categories') return Response.json([{ id: 1, name: 'Suppen' }]);
		if (pathname === '/api/recipes') {
			const page = Number(searchParams.get('page'));
			return Response.json({
				items: recipes.slice((page - 1) * 100, page * 100),
				total: recipes.length
			});
		}
		const recipeMatch = /^\/api\/recipes\/(\d+)$/.exec(pathname);
		if (recipeMatch) {
			const item = recipes.find(({ id }) => id === Number(recipeMatch[1]))!;
			return Response.json(editedDuringRead ? { ...item, version: item.version + 1 } : item);
		}
		if (pathname.endsWith('/ratings')) return Response.json(ratings);
		if (pathname.endsWith('/comments')) return Response.json([{ text: 'Muskat' }]);
		if (pathname === '/api/favorites')
			return Response.json(
				[...recipes].reverse().map(({ id }) => ({ recipe_id: id, user_id: user.id }))
			);
		if (pathname === '/api/favorites/preferences') return Response.json({ sort: 'manual' });
		if (pathname.startsWith('/media/'))
			return new Response(pathname, { headers: { 'Content-Type': 'image/jpeg' } });
		if (pathname === '/api/settings') return Response.json({ cookbook_name: 'Familienrezepte' });
		return Response.json({});
	});
	return {
		storage,
		fetcher,
		media,
		run: () => {
			authReads = 0;
			return syncOffline({ storage, user, fetcher: fetcher as unknown as typeof fetch });
		},
		update: (next: Recipe[]) => {
			recipes = next;
		},
		fail: (path: string | null) => {
			fail = path;
		},
		fill: (full: boolean) => {
			quota = full;
		},
		editDuringRead: () => {
			editedDuringRead = true;
		},
		switchAccount: () => {
			finalUser = { ...user, id: 8 };
		}
	};
}

it('requires an active approved account and exposes no data without a complete sync', async () => {
	const { storage, fetcher } = harness();
	expect(mayWorkOffline(null)).toBe(false);
	for (const account of [
		{ ...user, pending_approval: true },
		{ ...user, is_active: false }
	]) {
		expect(
			(await syncOffline({ storage, user: account, fetcher: fetcher as unknown as typeof fetch }))
				.ok
		).toBe(false);
	}
	expect(fetcher).not.toHaveBeenCalled();
	expect(await serveOffline(url('/api/recipes'), storage, user.id)).toBeNull();
	expect(await serveOffline(url('/media/recipe-images/1.jpg'), storage, user.id)).toBeNull();
});

it('serves legacy account snapshots using only the current account fields', async () => {
	const { run } = harness();
	const result = await run();
	if (!result.ok) throw new Error(result.error);
	const legacyUser = { ...user, email_verified_at: undefined, display_name: 'Lena Klarname' };
	const snapshot = { ...result.snapshot, user: legacyUser as unknown as User };
	const response = answerFromSnapshot(snapshot, url('/api/auth/me'));
	expect(await response?.json()).toEqual(user);
});

it('downloads every page and makes unseen pictures, comments, ratings and ordered favorites available', async () => {
	const all = Array.from({ length: 103 }, (_, i) => recipe(i + 1));
	all[102].images.unshift({ ...all[102].images[0], file_path: '/media/recipe-images/gallery.jpg' });
	const { storage, run } = harness(all);
	expect((await run()).ok).toBe(true);
	const list = await serveOffline(
		url('/api/recipes?summary=true&page_size=100&page=2'),
		storage,
		user.id
	);
	expect(await list!.json()).toMatchObject({
		total: 103,
		items: all.slice(100).map(({ id }) => ({ id }))
	});
	const detail = await serveOffline(url('/api/recipes/103'), storage, user.id);
	expect((await detail!.json()).images).toEqual(all[102].images);
	const image = await serveOffline(url('/media/recipe-images/gallery.jpg'), storage, user.id);
	expect(await image!.text()).toBe('/media/recipe-images/gallery.jpg');
	const comments = await serveOffline(url('/api/recipes/103/comments'), storage, user.id);
	expect(await comments!.json()).toEqual([{ text: 'Muskat' }]);
	const savedRatings = await serveOffline(url('/api/recipes/103/ratings'), storage, user.id);
	expect(savedRatings!.headers.get('X-Offline')).toBe('1');
	expect(await savedRatings!.json()).toEqual(ratings);
	const favorites = await serveOffline(url('/api/favorites?expected_user_id=7'), storage, user.id);
	expect((await favorites!.json()).slice(0, 2)).toEqual([
		{ recipe_id: 103, user_id: 7 },
		{ recipe_id: 102, user_id: 7 }
	]);
	expect(
		(await serveOffline(url('/api/favorites?expected_user_id=8'), storage, user.id))!.status
	).toBe(409);
	expect(await (await serveOffline(url('/api/settings'), storage, user.id))!.json()).toEqual({
		cookbook_name: 'Familienrezepte'
	});
});

it('keeps the previous ratings snapshot when a ratings request fails', async () => {
	const job = harness();
	const first = await job.run();
	if (!first.ok) throw new Error(first.error);
	job.fail('/api/recipes/2/ratings');
	expect((await job.run()).ok).toBe(false);
	expect(job.storage.commit).toHaveBeenCalledTimes(1);
	const saved = await serveOffline(url('/api/recipes/2/ratings'), job.storage, user.id);
	expect(await saved!.json()).toEqual(ratings);
	const legacy = { ...first.snapshot, ratings: undefined };
	expect(answerFromSnapshot(legacy, url('/api/recipes/2/ratings'))?.status).toBe(503);
	expect(answerFromSnapshot(legacy, url('/api/recipes/3/ratings'))?.status).toBe(404);
});

it('retains the previous generation through interrupted and quota-failed updates and replaces it on success', async () => {
	const job = harness();
	job.fail('/media/recipe-images/2.jpg');
	expect((await job.run()).ok).toBe(false);
	expect(job.storage.writeStatus).toHaveBeenLastCalledWith(
		expect.objectContaining({
			userId: user.id,
			state: 'failed'
		})
	);
	expect(await job.storage.readSnapshot(user.id)).toBeNull();
	expect(job.media.size).toBe(0);
	job.fail(null);
	expect((await job.run()).ok).toBe(true);
	const previous = await job.storage.readSnapshot(user.id);
	job.update([recipe(2, 'Geändert'), recipe(3)]);
	job.fail('/media/recipe-images/3.jpg');
	expect((await job.run()).ok).toBe(false);
	job.fail(null);
	job.fill(true);
	expect((await job.run()).ok).toBe(false);
	expect(await job.storage.readSnapshot(user.id)).toBe(previous);
	expect(job.media.size).toBe(1);
	job.fill(false);
	expect((await job.run()).ok).toBe(true);
	expect(
		(await job.storage.readSnapshot(user.id))!.recipes.map(({ id, title }) => [id, title])
	).toEqual([
		[2, 'Geändert'],
		[3, 'Suppe']
	]);
});

it('does not commit if the authenticated account changed during the download', async () => {
	const job = harness();
	job.switchAccount();
	expect((await job.run()).ok).toBe(false);
	expect(job.storage.commit).not.toHaveBeenCalled();
});

it('does not commit an incomplete paginated response', async () => {
	const job = harness();
	job.fetcher.mockImplementation(async (input) =>
		input === '/api/auth/me'
			? Response.json(user)
			: input.startsWith('/api/recipes?')
				? Response.json({ items: [], total: 100 })
				: Response.json([])
	);
	expect((await job.run()).ok).toBe(false);
	expect(job.storage.commit).not.toHaveBeenCalled();
});

it('ranks folded title, ingredient and comment matches and returns category links only for zero local hits', async () => {
	const recipes = [
		recipe(1, 'Suppe', 2),
		recipe(2, 'Zutaten', 2),
		recipe(3, 'Käsespätzle', 3),
		recipe(4, 'Käsespätzle', 2)
	];
	recipes[1].ingredients = [{ name: 'Käsespätzle' } as Recipe['ingredients'][number]];
	const snapshot = {
		recipes,
		summaries: recipes,
		manualOrder: { 2: [1, 2, 4] },
		categories: [
			{ id: 1, name: 'Grillen' },
			{ id: 2, name: 'Abendessen' },
			{ id: 3, name: 'Mittag' }
		],
		comments: { 1: [{ text: 'Käsespätzle mit Muskat' }] }
	} as unknown as OfflineSnapshot;
	const find = async (query: string) =>
		answerFromSnapshot(snapshot, url('/api/recipes?' + query))!.json();
	expect(
		(await find('search=KASESPATZLE&category_id=2&sort=manual')).items.map(({ id }: Recipe) => id)
	).toEqual([4, 2, 1]);
	expect((await find('search=kasespatzle')).total).toBe(4);
	expect(await find('search=kasespatzle&category_id=1')).toMatchObject({
		items: [],
		other_categories: [
			{ id: 2, name: 'Abendessen', count: 3 },
			{ id: 3, name: 'Mittag', count: 1 }
		]
	});
	expect(await find('search=Muskat')).toMatchObject({ total: 1 });
	expect(await find('search=Fehlt')).toMatchObject({ total: 0, other_categories: [] });
});

it('keeps the previous images available after publishing a new generation', async () => {
	const job = harness();
	await job.run();
	const previous = (await job.storage.readSnapshot(user.id))!.generation;
	job.update([recipe(2)]);
	expect((await job.run()).ok).toBe(true);
	expect(job.media.has(previous)).toBe(true);
	const path = url('/media/recipe-images/1.jpg');
	expect(await (await serveOffline(path, job.storage, user.id))!.text()).toBe(path.pathname);
	expect(await serveOffline(path, job.storage, user.id + 1)).toBeNull();
	expect((await job.run()).ok).toBe(true);
	expect(job.media.has(previous)).toBe(false);
	expect(job.media.size).toBe(2);
});

it('fails if a recipe changes while comments are being read', async () => {
	const job = harness();
	job.editDuringRead();
	expect((await job.run()).ok).toBe(false);
	expect(job.storage.commit).not.toHaveBeenCalled();
});

it('matches the server folding for sharp s, umlauts and unmapped letters', () => {
	expect(foldText('\u00c4\u00e9\u1e9e\u00df \u00d8\u00f8 \u0141\u0142 \u00c6')).toBe(
		'assss \u00f8\u00f8 \u0142\u0142 \u00e6'
	);
	const input = String.fromCodePoint(...Array.from({ length: 0xc0 }, (_, i) => 0xc0 + i), 0x1e9e);
	// SHA-256 of recipe_service._fold_term(input) encoded as UTF-8.
	expect(createHash('sha256').update(foldText(input)).digest('hex')).toBe(
		'f9559d06eb9172f7c789b00b5eda24955cce186d0c9de2415e42c8a619a03a33'
	);
});


it('searches umlaut spellings, ingredient groups and day titles with server relevance', () => {
    expect(foldText('KAeSE Öl Oel Grünkohl Gruenkohl')).toBe('kase ol ol grunkohl grunkohl');
    const grouped = { ...recipe(1), ingredient_groups: [{ name: 'Füllung' }] } as Recipe;
    const planned = { ...recipe(2), day_titles: ['Füllung vorbereiten'] };
    expect(searchRelevance(grouped, [], 'fuellung')).toBe(1);
    expect(searchRelevance(planned, [], 'fuellung')).toBe(2);
    expect(searchRelevance(recipe(3), [], 'fuellung')).toBeNull();
});
