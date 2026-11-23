import { offline } from '$lib/stores/offline.svelte';
import { beforeEach, expect, test, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import Favorites from '../../src/routes/favorites/+page.svelte';
import { page } from './navigation.svelte';
import { auth } from '../../src/lib/stores/auth.svelte';
import * as api from '../../src/lib/api';
vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	getRecipe: vi.fn(),
	getCurrentUser: vi.fn(),
	listFavorites: vi.fn(),
	getFavoritePreferences: vi.fn(),
	updateFavoritePreferences: vi.fn(),
	setFavoriteOrder: vi.fn()
}));
beforeEach(() => {
	localStorage.clear();
	vi.clearAllMocks();
	vi.mocked(api.getFavoritePreferences).mockResolvedValue({ sort: 'recent', recipe_view: 'list' });
	vi.mocked(api.updateFavoritePreferences).mockResolvedValue(undefined);
	auth.initialized = true;
	auth.loading = false;
	auth.user = {
		id: 1,
		username: 'reader',
		email: null,
		email_verified_at: null,
		role: 'reader',
		is_active: true,
		pending_approval: false,
		created_at: ''
	};
	vi.mocked(api.listFavorites).mockResolvedValue(
		Array.from({ length: 45 }, (_, index) => favorite(index + 1))
	);
	vi.mocked(api.getRecipe).mockImplementation(
		async (id) =>
			({
				id,
				title: `Favorit ${id}`,
				images: [],
				preparation_days: 2,
				origin_person: 'Oma',
				category: { name: 'Brot' }
			}) as never
	);
});
function favorite(id: number, userId = 1) {
	return { id, recipe_id: id, user_id: userId, created_at: null };
}

function visibleFavorites() {
	return screen
		.getAllByRole('link', { name: /Favorit \d/ })
		.map((link) => new URL((link as HTMLAnchorElement).href).pathname);
}

test('favorite recipe links provide a return to the favorites overview', async () => {
	render(Favorites);
	const recipe = await screen.findByRole<HTMLAnchorElement>('link', { name: /Favorit 1 / });
	expect(new URL(recipe.href).searchParams.get('returnTo')).toBe('/favorites');
});

test('favorites use the compact list and bounded loading, retrying failed batches without losing recipes', async () => {
	render(Favorites);
	await screen.findByRole('link', { name: /Favorit 20 / });
	expect(api.getRecipe).toHaveBeenCalledTimes(20);
	expect(document.querySelector('.recipe-grid.list')).toBeTruthy();
	vi.mocked(api.getRecipe).mockRejectedValueOnce(new Error('temporary'));
	await fireEvent.click(screen.getByRole('button', { name: 'Weitere Rezepte laden' }));
	await screen.findByText(/Versuch es erneut/);
	expect(screen.getAllByRole('link', { name: /Favorit \d/ })).toHaveLength(20);
	await fireEvent.click(screen.getByRole('button', { name: 'Weitere Rezepte laden' }));
	await screen.findByRole('link', { name: /Favorit 40 / });
	await fireEvent.click(screen.getByRole('button', { name: 'Weitere Rezepte laden' }));
	await waitFor(() => expect(screen.getAllByRole('link', { name: /Favorit \d/ })).toHaveLength(45));
	expect(screen.queryByRole('button', { name: 'Weitere Rezepte laden' })).toBeNull();
});

test('sort, view, and manual ordering use the account preferences', async () => {
	const favorites = [favorite(3), favorite(2), favorite(1)];
	vi.mocked(api.listFavorites).mockImplementation(async (sort) =>
		sort === 'recent' ? favorites : [favorites[2], favorites[1], favorites[0]]
	);
	vi.mocked(api.setFavoriteOrder).mockResolvedValue([favorites[1], favorites[2], favorites[0]]);

	render(Favorites);
	await screen.findByRole('link', { name: /Favorit 3 / });
	expect(visibleFavorites()).toEqual(['/recipes/3', '/recipes/2', '/recipes/1']);
	await fireEvent.click(screen.getByRole('button', { name: 'A–Z' }));
	await waitFor(() =>
		expect(visibleFavorites()).toEqual(['/recipes/1', '/recipes/2', '/recipes/3'])
	);
	expect(api.listFavorites).toHaveBeenCalledWith('name', 1);
	expect(api.updateFavoritePreferences).toHaveBeenCalledWith(1, { sort: 'name' });

	await fireEvent.click(screen.getByRole('button', { name: 'Eigene Sortierung' }));
	await fireEvent.click(await screen.findByRole('button', { name: 'Reihenfolge ändern' }));
	await fireEvent.click(screen.getByRole('button', { name: 'Favorit 2 · Oma nach oben' }));
	await fireEvent.click(screen.getByRole('button', { name: 'Reihenfolge speichern' }));
	await screen.findByRole('button', { name: 'Reihenfolge ändern' });
	expect(api.setFavoriteOrder).toHaveBeenCalledWith(1, [2, 1, 3]);
	expect(visibleFavorites()).toEqual(['/recipes/2', '/recipes/1', '/recipes/3']);

	await fireEvent.click(screen.getByRole('button', { name: 'Kachelansicht' }));
	await waitFor(() => expect(document.querySelector('.recipe-grid.list')).toBeNull());
	expect(screen.getByRole('button', { name: 'Kachelansicht', pressed: true })).toBeTruthy();
	expect(api.updateFavoritePreferences).toHaveBeenCalledWith(1, { recipe_view: 'grid' });
});

test('the view toggle is disabled while saving and retains the saved layout after a failure', async () => {
	let rejectSave!: (error: Error) => void;
	vi.mocked(api.updateFavoritePreferences).mockReturnValueOnce(new Promise((_, reject) => {
		rejectSave = reject;
	}));
	render(Favorites);
	await screen.findByRole('link', { name: /Favorit 1 / });
	await fireEvent.click(screen.getByRole('button', { name: 'Kachelansicht' }));
	expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Kachelansicht' }).disabled).toBe(true);
	expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Listenansicht' }).disabled).toBe(true);
	rejectSave(new Error('temporary'));
	await screen.findByText('Die Ansicht konnte nicht gespeichert werden.');
	expect(screen.getByRole('button', { name: 'Listenansicht', pressed: true })).toBeTruthy();
	expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Kachelansicht' }).disabled).toBe(false);
	expect(document.querySelector('.recipe-grid.list')).toBeTruthy();
});

test('account changes discard the previous favorites and guests are redirected', async () => {
	vi.mocked(api.getFavoritePreferences).mockResolvedValueOnce({
		sort: 'manual',
		recipe_view: 'grid'
	});
	vi.mocked(api.listFavorites).mockResolvedValueOnce([favorite(1)]);
	render(Favorites);
	await screen.findByRole('link', { name: /Favorit 1 / });
	expect(
		screen.getByRole('button', { name: 'Eigene Sortierung' }).getAttribute('aria-pressed')
	).toBe('true');
	expect(document.querySelector('.recipe-grid.list')).toBeNull();

	vi.mocked(api.listFavorites).mockResolvedValueOnce([favorite(99, 2)]);
	auth.user = { ...auth.user!, id: 2 };
	await screen.findByRole('link', { name: /Favorit 99 / });
	expect(api.getFavoritePreferences).toHaveBeenLastCalledWith(2);
	expect(visibleFavorites()).toEqual(['/recipes/99']);
	expect(document.querySelector('.recipe-grid.list')).toBeTruthy();

	auth.user = null;
	await waitFor(() => expect(page.url.pathname).toBe('/login'));
	expect(screen.queryByRole('link', { name: /Favorit 99 / })).toBeNull();
});


test('refreshes the signed-in account when a favorite request rejects a stale tab', async () => {
	vi.mocked(api.getCurrentUser).mockResolvedValueOnce({ ...auth.user!, id: 2 });
	vi.mocked(api.listFavorites).mockImplementation(async (sort, userId) => {
		if (userId === 2) return [favorite(99, 2)];
		if (sort === 'name') throw new api.ApiError(403, 'The signed-in account has changed.');
		return [favorite(1)];
	});
	render(Favorites);
	await screen.findByRole('link', { name: /Favorit 1 / });
	await fireEvent.click(screen.getByRole('button', { name: 'A–Z' }));
	await screen.findByRole('link', { name: /Favorit 99 / });
	expect(visibleFavorites()).toEqual(['/recipes/99']);
	expect(api.updateFavoritePreferences).not.toHaveBeenCalled();
});

test('keeps an open favorites view in sync with the published generation', async () => {
	render(Favorites);
	await screen.findByRole('link', { name: /Favorit 20 / });
	vi.mocked(api.listFavorites).mockResolvedValue([favorite(45)]);
	try {
		offline.generation = 'new-favorites-generation';
		await screen.findByRole('link', { name: /Favorit 45 / });
		expect(visibleFavorites()).toEqual(['/recipes/45']);
	} finally {
		offline.generation = null;
	}
});
