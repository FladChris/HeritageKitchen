import { beforeEach, expect, test, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/svelte';
import OrderList from '$lib/components/OrderList.svelte';
import Home from '../../src/routes/+page.svelte';
import { page } from './navigation.svelte';
import { auth } from '../../src/lib/stores/auth.svelte';
import * as api from '../../src/lib/api';
import type { Category, UserRole } from '../../src/lib/types';

vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	listCategories: vi.fn(),
	listRecipes: vi.fn(async () => ({ items: [], total: 0, page: 1, page_size: 20 })),
	deleteCategory: vi.fn(),
	getViewPreferences: vi.fn(),
	updateViewPreferences: vi.fn()
}));

const categories: Category[] = [
	{ id: 2, name: 'Brot', recipe_count: 2 },
	{ id: 1, name: 'Zucchini', recipe_count: 10 },
	{ id: 4, name: 'Dessert', recipe_count: 0 },
	{ id: 3, name: 'Äpfel', recipe_count: 4 }
].map((category) => ({ ...category, description: null, image_path: null, image_alt_text: null }));

function displayedIds() {
	return screen
		.getAllByRole('link')
		.map((link) => link.getAttribute('href'))
		.filter((href) => href?.startsWith('/?category='));
}

beforeEach(() => {
	vi.clearAllMocks();
	localStorage.clear();
	page.url = new URL('http://localhost/');
	auth.user = null;
	auth.initialized = true;
	auth.loading = false;
	vi.mocked(api.listCategories).mockResolvedValue(structuredClone(categories));
	vi.mocked(api.getViewPreferences).mockResolvedValue({
		category_sort: 'manual',
		recipe_view: 'list',
		category_ids: categories.map(({ id }) => id)
	});
	vi.mocked(api.updateViewPreferences).mockResolvedValue(undefined);
	vi.mocked(api.deleteCategory).mockResolvedValue(undefined);
});

async function sortBy(label: string) {
	const group = await screen.findByRole('group', { name: 'Kategorien sortieren' });
	await fireEvent.click(within(group).getByRole('button', { name: label }));
}

test('guests can sort by name or recipe count without storing a preference', async () => {
	localStorage.setItem('heritagekitchen:category-sort', 'manual');
	render(Home);
	const group = await screen.findByRole('group', { name: 'Kategorien sortieren' });
	expect(within(group).queryByRole('button', { name: /^Eigene/ })).toBeNull();
	expect(
		within(group)
			.getAllByRole('button')
			.map((button) => button.textContent?.trim())
	).toEqual(['A–Z', 'Meiste Rezepte']);
	expect(displayedIds()).toEqual(['/?category=3', '/?category=2', '/?category=4', '/?category=1']);
	expect(within(group).getByRole('button', { name: 'A–Z', pressed: true })).toBeTruthy();
	await sortBy('Meiste Rezepte');
	expect(displayedIds()).toEqual(['/?category=1', '/?category=3', '/?category=2', '/?category=4']);
	expect(screen.getByRole('link', { name: 'Zucchini 10 Rezepte' })).toBeTruthy();
	expect(within(group).getByRole('button', { name: 'Meiste Rezepte', pressed: true })).toBeTruthy();
	expect(localStorage.getItem('heritagekitchen:category-sort')).toBe('manual');
	expect(api.getViewPreferences).not.toHaveBeenCalled();
	expect(api.updateViewPreferences).not.toHaveBeenCalled();
	expect(screen.queryByRole('button', { name: 'Reihenfolge ändern' })).toBeNull();
	await sortBy('A–Z');
	expect(displayedIds()[0]).toBe('/?category=3');
});

test('restores the account count mode and uses fresh counts when returning to the overview', async () => {
	auth.user = user(1);
	vi.mocked(api.getViewPreferences).mockResolvedValue({
		category_sort: 'count',
		recipe_view: 'list',
		category_ids: [2, 1, 4, 3]
	});
	const firstVisit = render(Home);
	await screen.findByRole('button', { name: 'Meiste Rezepte', pressed: true });
	expect(displayedIds()[0]).toBe('/?category=1');
	firstVisit.unmount();
	vi.mocked(api.listCategories).mockResolvedValue(
		categories.map((category) => ({
			...category,
			recipe_count: category.id === 2 ? 12 : category.recipe_count
		}))
	);
	render(Home);
	await screen.findByRole('button', { name: 'Meiste Rezepte', pressed: true });
	expect(displayedIds()[0]).toBe('/?category=2');
	expect(screen.getByRole('link', { name: 'Brot 12 Rezepte' })).toBeTruthy();
	await sortBy('Eigene');
	expect(displayedIds()).toEqual(['/?category=2', '/?category=1', '/?category=4', '/?category=3']);
	expect(api.updateViewPreferences).toHaveBeenLastCalledWith(1, { category_sort: 'manual' });
	await sortBy('Meiste Rezepte');
	expect(api.updateViewPreferences).toHaveBeenLastCalledWith(1, { category_sort: 'count' });
});

function user(id: number, role: UserRole = 'reader') {
	return {
		id,
		username: `user${id}`,
		role,
		is_active: true,
		pending_approval: false,
		email: null,
		email_verified_at: null,
		created_at: ''
	};
}

test.each<UserRole>(['reader', 'editor'])(
	'allows %s to reorder but not manage categories',
	async (role) => {
		auth.user = user(1, role);
		render(Home);
		const actions = await screen.findByRole('group', { name: 'Kategorieaktionen' });
		expect(within(actions).getByRole('button', { name: 'Reihenfolge ändern' })).toBeTruthy();
		expect(within(actions).queryByRole('button', { name: 'Kategorie hinzufügen' })).toBeNull();
		expect(
			within(actions).queryByRole('button', { name: 'Gemeinsame Reihenfolge ändern' })
		).toBeNull();
		page.url = new URL('http://localhost/?category=4');
		await screen.findByRole('heading', { name: 'Dessert' });
		expect(screen.queryByRole('button', { name: 'Kategorie umbenennen' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'Kategorie löschen' })).toBeNull();
	}
);

test('an admin can manage categories and must confirm deletion of an empty category', async () => {
	auth.user = user(1, 'admin');
	vi.mocked(api.listCategories).mockResolvedValue(
		categories.map((category) =>
			category.id === 4 ? { ...category, image_path: '/image.jpg' } : category
		)
	);
	render(Home);
	expect(await screen.findByRole('button', { name: 'Kategorie hinzufügen' })).toBeTruthy();
	page.url = new URL('http://localhost/?category=4');
	await fireEvent.click(await screen.findByRole('button', { name: 'Kategorie umbenennen' }));
	expect(screen.getByLabelText('Kategoriename')).toBeTruthy();
	expect(screen.getByLabelText('Bild ändern')).toBeTruthy();
	expect(screen.getByRole('button', { name: 'Bild entfernen' })).toBeTruthy();
	await fireEvent.click(screen.getByRole('button', { name: 'Abbrechen' }));
	const remove = screen.getByRole('button', { name: 'Kategorie löschen' });
	await fireEvent.click(remove);
	const dialog = await screen.findByRole('dialog', { name: 'Kategorie löschen?' });
	expect(api.deleteCategory).not.toHaveBeenCalled();
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Abbrechen' }));
	expect(api.deleteCategory).not.toHaveBeenCalled();
	await fireEvent.click(remove);
	const confirmation = await screen.findByRole('button', { name: 'Endgültig löschen' });
	await fireEvent.click(confirmation);
	expect(api.deleteCategory).toHaveBeenCalledExactlyOnceWith(4);
	await waitFor(() => expect(page.url.pathname + page.url.search).toBe('/'));
});

test('a reader automatically saves each move and can retry a failed save', async () => {
	auth.user = user(1);
	vi.mocked(api.updateViewPreferences).mockRejectedValueOnce(new api.ApiError(500, 'offline'));
	render(Home);
	const edit = await screen.findByRole('button', { name: 'Reihenfolge ändern' });
	await waitFor(() => expect((edit as HTMLButtonElement).disabled).toBe(false));
	expect(screen.queryByRole('button', { name: 'Gemeinsame Reihenfolge ändern' })).toBeNull();
	await fireEvent.click(edit);
	const down = screen.getByRole('button', { name: 'Brot nach unten' });
	down.focus();
	expect(document.activeElement).toBe(down);
	await fireEvent.click(down);
	expect(screen.getByText('Brot: Position 2 von 4.').getAttribute('role')).toBe('status');
	expect(document.activeElement).toBe(down);
	const update = { category_sort: 'manual', category_order: { category_ids: [1, 2, 4, 3] } };
	expect(api.updateViewPreferences).toHaveBeenCalledWith(1, update);
	await screen.findByRole('alert');
	await fireEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }));
	expect(api.updateViewPreferences).toHaveBeenNthCalledWith(2, 1, update);
	await fireEvent.click(screen.getByRole('button', { name: 'Fertig' }));
	expect(displayedIds()[0]).toBe('/?category=1');
});

test('dragging saves on release and a cancelled drag restores the last order', async () => {
	auth.user = user(1);
	render(Home);
	const edit = await screen.findByRole('button', { name: 'Reihenfolge ändern' });
	await waitFor(() => expect((edit as HTMLButtonElement).disabled).toBe(false));
	await fireEvent.click(edit);
	const list = screen.getByRole('list');
	const rows = within(list).getAllByRole('listitem');
	for (const [index, row] of rows.entries()) {
		vi.spyOn(row, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, index * 40, 100, 40));
	}
	const grip = rows[0].querySelector<HTMLElement>('.grip')!;
	grip.setPointerCapture = vi.fn();
	const move = () =>
		fireEvent(list, new MouseEvent('pointermove', { bubbles: true, clientY: 200 }));
	await fireEvent.pointerDown(grip);
	await move();
	expect(api.updateViewPreferences).not.toHaveBeenCalled();
	await fireEvent.pointerCancel(list);
	expect(within(list).getAllByRole('listitem')[0]).toBe(rows[0]);
	await fireEvent.pointerDown(grip);
	await move();
	await fireEvent.pointerUp(list);
	expect(api.updateViewPreferences).toHaveBeenCalledExactlyOnceWith(1, {
		category_sort: 'manual',
		category_order: { category_ids: [1, 4, 3, 2] }
	});
});

test('applies stored order, appends new categories and isolates a switch in the same browser', async () => {
	auth.user = user(1);
	localStorage.setItem('heritagekitchen:category-sort', 'name');
	vi.mocked(api.getViewPreferences).mockResolvedValueOnce({
		category_sort: 'manual',
		recipe_view: 'grid',
		category_ids: [4, 99, 1]
	});
	vi.mocked(api.getViewPreferences).mockResolvedValueOnce({
		category_sort: 'name',
		recipe_view: 'list',
		category_ids: []
	});
	render(Home);
	await waitFor(() =>
		expect(displayedIds()).toEqual(['/?category=4', '/?category=1', '/?category=2', '/?category=3'])
	);
	await sortBy('A–Z');
	expect(api.updateViewPreferences).toHaveBeenCalledWith(1, { category_sort: 'name' });
	auth.user = user(2);
	await waitFor(() => expect(api.getViewPreferences).toHaveBeenCalledWith(2));
	await screen.findByRole('button', { name: 'A–Z', pressed: true });
	expect(displayedIds()[0]).toBe('/?category=3');
});

test('loads the recipe view from the account and saves a toggle immediately', async () => {
	auth.user = user(1);
	page.url = new URL('http://localhost/?category=2');
	localStorage.setItem('heritagekitchen:recipe-view', 'list');
	vi.mocked(api.getViewPreferences).mockResolvedValueOnce({
		category_sort: 'manual',
		recipe_view: 'grid',
		category_ids: []
	});
	vi.mocked(api.listRecipes).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 20 });
	let resolveRecipes!: (value: Awaited<ReturnType<typeof api.listRecipes>>) => void;
	vi.mocked(api.listRecipes).mockImplementationOnce(
		() =>
			new Promise((resolve) => {
				resolveRecipes = resolve;
			})
	);
	render(Home);
	await screen.findByRole('button', { name: 'Kachelansicht', pressed: true });
	await fireEvent.click(screen.getByRole('button', { name: 'Listenansicht' }));
	expect(api.updateViewPreferences).toHaveBeenCalledWith(1, { recipe_view: 'list' });
	resolveRecipes({ items: [], total: 0, page: 1, page_size: 20 });
});

test('moving an item to the boundary keeps focus on its available direction', async () => {
	const onchange = vi.fn();
	render(OrderList, { items: [{ id: 1, name: 'Brot' }, { id: 2, name: 'Dessert' }], onchange });
	const move = screen.getByRole('button', { name: 'Brot nach unten' });
	move.focus();
	await fireEvent.click(move);
	expect(onchange).toHaveBeenCalledWith([2, 1]);
	expect(screen.getByRole('status').textContent).toBe('Brot: Position 2 von 2.');
	expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Brot nach oben' }));
});
