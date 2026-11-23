import { beforeEach, expect, test, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/svelte';
import Home from '../../src/routes/+page.svelte';
import { page } from './navigation.svelte';
import { auth } from '../../src/lib/stores/auth.svelte';
import * as api from '../../src/lib/api';
import type { RecipeSummary, UserRole } from '../../src/lib/types';

vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	listCategories: vi.fn(),
	listRecipes: vi.fn(),
	saveRecipeOrder: vi.fn(),
	getViewPreferences: vi.fn(),
	updateViewPreferences: vi.fn()
}));

function recipe(id: number, title: string): RecipeSummary {
	return {
		id,
		version: 1,
		title,
		summary: null,
		preparation_days: 1,
		preparation_time: null,
		cooking_time: null,
		cooking_time_max: null,
		rest_time: null,
		rest_time_max: null,
		servings: null,
		origin_person: null,
		category_id: 1,
		created_at: '',
		updated_at: '',
		category: null,
		images: []
	};
}

const alphabetical = [recipe(1, 'Apfelkuchen'), recipe(2, 'Bienenstich'), recipe(3, 'Mohnkuchen')];
const personal = [alphabetical[2], alphabetical[0], alphabetical[1]];

function user(role: UserRole) {
	return {
		id: 1,
		username: 'lena',
		role,
		is_active: true,
		pending_approval: false,
		email: null,
		email_verified_at: null,
		created_at: ''
	};
}

function shownTitles() {
	return screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent);
}

beforeEach(() => {
	vi.clearAllMocks();
	localStorage.clear();
	page.url = new URL('http://localhost/?category=1');
	auth.user = null;
	auth.initialized = true;
	auth.loading = false;
	vi.mocked(api.listCategories).mockResolvedValue([
		{ id: 1, name: 'Kuchen', recipe_count: 3, description: null, image_path: null, image_alt_text: null }
	]);
	vi.mocked(api.getViewPreferences).mockResolvedValue({
		category_sort: 'name',
		recipe_view: 'list',
		category_ids: []
	});
	vi.mocked(api.listRecipes).mockImplementation(async (params) => ({
		items: params.sort === 'manual' ? personal : alphabetical,
		total: 3,
		page: 1,
		page_size: params.page_size ?? 20
	}));
	vi.mocked(api.saveRecipeOrder).mockResolvedValue(undefined);
});

test('guests only get the A–Z recipe sort', async () => {
	render(Home);
	await screen.findByText('Apfelkuchen');
	const group = screen.getByRole('group', { name: 'Rezepte sortieren' });
	expect(within(group).getAllByRole('button').map((button) => button.textContent?.trim())).toEqual(['A–Z']);
	expect(screen.queryByRole('button', { name: 'Reihenfolge ändern' })).toBeNull();
});

test('signed-in users switch to their own order and save moves per category', async () => {
	auth.user = user('reader');
	render(Home);
	await screen.findByText('Apfelkuchen');
	const group = screen.getByRole('group', { name: 'Rezepte sortieren' });
	await fireEvent.click(within(group).getByRole('button', { name: 'Eigene' }));
	await waitFor(() => expect(shownTitles()).toEqual(['Mohnkuchen', 'Apfelkuchen', 'Bienenstich']));
	expect(api.listRecipes).toHaveBeenLastCalledWith(
		expect.objectContaining({ sort: 'manual', category_id: 1 })
	);

	await fireEvent.click(screen.getByRole('button', { name: 'Reihenfolge ändern' }));
	const move = await screen.findByRole('button', { name: 'Bienenstich nach oben' });
	move.focus();
	expect(document.activeElement).toBe(move);
	await fireEvent.click(move);
	expect(screen.getByText('Bienenstich: Position 2 von 3.').getAttribute('role')).toBe('status');
	await waitFor(() => expect(api.saveRecipeOrder).toHaveBeenCalledWith(1, [3, 2, 1]));
	expect(api.updateViewPreferences).not.toHaveBeenCalled();
});

test('the recipe order is not offered while searching', async () => {
	auth.user = user('reader');
	render(Home);
	await screen.findByText('Apfelkuchen');
	const group = screen.getByRole('group', { name: 'Rezepte sortieren' });
	await fireEvent.click(within(group).getByRole('button', { name: 'Eigene' }));
	await screen.findByRole('button', { name: 'Reihenfolge ändern' });
	await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'kuchen' } });
	await waitFor(() => expect(screen.queryByRole('button', { name: 'Reihenfolge ändern' })).toBeNull());
});

test('recipe order saves are sent one at a time and the latest order wins', async () => {
	auth.user = user('reader');
	const releases: (() => void)[] = [];
	vi.mocked(api.saveRecipeOrder).mockImplementation(
		() => new Promise<void>((resolve) => releases.push(resolve))
	);
	render(Home);
	await screen.findByText('Apfelkuchen');
	const group = screen.getByRole('group', { name: 'Rezepte sortieren' });
	await fireEvent.click(within(group).getByRole('button', { name: 'Eigene' }));
	await fireEvent.click(await screen.findByRole('button', { name: 'Reihenfolge ändern' }));
	await fireEvent.click(await screen.findByRole('button', { name: 'Bienenstich nach oben' }));
	await fireEvent.click(await screen.findByRole('button', { name: 'Bienenstich nach oben' }));
	await fireEvent.click(await screen.findByRole('button', { name: 'Mohnkuchen nach unten' }));
	expect(api.saveRecipeOrder).toHaveBeenCalledTimes(1);
	expect(api.saveRecipeOrder).toHaveBeenLastCalledWith(1, [3, 2, 1]);
	releases[0]();
	await waitFor(() => expect(api.saveRecipeOrder).toHaveBeenCalledTimes(2));
	expect(api.saveRecipeOrder).toHaveBeenLastCalledWith(1, [2, 1, 3]);
	releases[1]();
});
