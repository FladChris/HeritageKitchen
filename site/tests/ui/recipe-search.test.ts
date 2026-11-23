import { beforeEach, expect, test, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import Home from '../../src/routes/+page.svelte';
import { page } from './navigation.svelte';
import { auth } from '../../src/lib/stores/auth.svelte';
import * as api from '../../src/lib/api';

vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	listCategories: vi.fn(),
	listRecipes: vi.fn(),
	getViewPreferences: vi.fn(),
	updateViewPreferences: vi.fn()
}));

beforeEach(() => {
	vi.clearAllMocks();
	localStorage.clear();
	page.url = new URL('http://localhost/?category=1');
	auth.user = null;
	auth.initialized = true;
	auth.loading = false;
	vi.mocked(api.listCategories).mockResolvedValue([
		{ id: 1, name: 'Grillen', recipe_count: 3, description: null, image_path: null, image_alt_text: null },
		{ id: 2, name: 'Backen', recipe_count: 4, description: null, image_path: null, image_alt_text: null }
	]);
	vi.mocked(api.getViewPreferences).mockResolvedValue({
		category_sort: 'name',
		recipe_view: 'list',
		category_ids: []
	});
});

test('an empty search in a category only links other categories with hit counts', async () => {
	vi.mocked(api.listRecipes).mockImplementation(async (params) => ({
		items: [],
		total: 0,
		other_categories: params.search ? [{ id: 2, name: 'Backen', count: 4 }] : [],
		page: 1,
		page_size: 20
	}));
	render(Home);
	await fireEvent.input(await screen.findByRole('searchbox'), { target: { value: 'Brot' } });
	const link = await screen.findByRole('link', { name: 'Backen – 4 Treffer' });
	expect(link.getAttribute('href')).toBe('/?category=2&search=Brot');
	expect(screen.queryByRole('heading', { level: 3 })).toBeNull();
});

test('no hits anywhere shows the plain empty state without category links', async () => {
	vi.mocked(api.listRecipes).mockResolvedValue({
		items: [],
		total: 0,
		other_categories: [],
		page: 1,
		page_size: 20
	});
	render(Home);
	await fireEvent.input(await screen.findByRole('searchbox'), { target: { value: 'Zzz' } });
	await screen.findByText('Keine Rezepte zu deiner Suche gefunden.');
	await waitFor(() => expect(screen.queryByRole('link', { name: /Treffer/ })).toBeNull());
});

test('a category link from an empty search opens that category with the same term', async () => {
	page.url = new URL('http://localhost/?category=2&search=Brot');
	vi.mocked(api.listRecipes).mockResolvedValue({
		items: [],
		total: 0,
		other_categories: [],
		page: 1,
		page_size: 20
	});
	render(Home);
	await waitFor(() =>
		expect(api.listRecipes).toHaveBeenCalledWith(
			expect.objectContaining({ search: 'Brot', category_id: 2 })
		)
	);
	expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('Brot');
});

test.each([
	['', '/?search=%C3%84pfel+%26+Brot'],
	['?category=2', '/?category=2&search=%C3%84pfel+%26+Brot']
])('recipe links retain the active search in the overview (%s)', async (query, expected) => {
	page.url = new URL(`http://localhost/${query}`);
	vi.mocked(api.listRecipes).mockImplementation(async (params) => ({
		items: params.search ? [{
			id: 7, title: 'Apfelbrot', category: { id: 2, name: 'Backen' }, images: [],
			preparation_days: 1
		} as never] : [],
		total: params.search ? 1 : 0,
		page: 1,
		page_size: 20
	}));
	render(Home);
	await fireEvent.input(await screen.findByRole('searchbox'), { target: { value: 'Äpfel & Brot' } });
	const link = await screen.findByRole('link', { name: /Apfelbrot/ });
	const href = new URL(link.getAttribute('href')!, page.url);
	expect(href.pathname).toBe('/recipes/7');
	expect(href.searchParams.get('returnTo')).toBe(expected);
});
