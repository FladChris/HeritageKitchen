import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import Home from '../../src/routes/+page.svelte';
import NewRecipe from '../../src/routes/recipes/new/+page.svelte';
import * as api from '../../src/lib/api';
import { auth } from '../../src/lib/stores/auth.svelte';
import type { Category } from '../../src/lib/types';
import { page } from './navigation.svelte';

vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	listCategories: vi.fn(),
	listRecipes: vi.fn(async () => ({ items: [], total: 0, page: 1, page_size: 20 })),
	getViewPreferences: vi.fn(async () => ({
		category_sort: 'manual',
		recipe_view: 'list',
		category_ids: []
	})),
	createCategory: vi.fn(),
	updateCategory: vi.fn(),
	setCategoryImage: vi.fn(),
	removeCategoryImage: vi.fn(),
	deleteCategory: vi.fn(),
	createRecipe: vi.fn()
}));

vi.mock('cropperjs', () => ({
	default: class {
		destroy() {}
		getCroppedCanvas() {
			return { toBlob: (done: (blob: Blob) => void) => done(new Blob(['cropped'])) };
		}
	}
}));

const kitchen: Category = {
	id: 1,
	name: 'Küche',
	description: null,
	image_path: null,
	image_alt_text: null,
	recipe_count: 0
};

beforeEach(() => {
	vi.clearAllMocks();
	page.url = new URL('http://localhost/');
	auth.initialized = true;
	auth.loading = false;
	auth.user = {
		id: 1,
		username: 'petra',
		email_verified_at: null,
		email: null,
		role: 'admin',
		created_at: '',
		is_active: true,
		pending_approval: false
	};
	vi.mocked(api.listCategories).mockResolvedValue([kitchen]);
});

afterEach(() => vi.unstubAllGlobals());

test('an empty category stays visible with a quiet image placeholder', async () => {
	render(Home);
	const category = await screen.findByRole('link', { name: 'Küche Noch keine Rezepte' });
	expect(category.querySelector('.photo-placeholder')).toBeTruthy();
	page.url = new URL(category.getAttribute('href')!, 'http://localhost/');
	expect(await screen.findByText('In dieser Kategorie gibt es noch keine Rezepte.')).toBeTruthy();
});

test('a duplicate name is explained in the create dialog without clearing the entry', async () => {
	vi.mocked(api.createCategory).mockRejectedValueOnce(
		new api.ApiError(409, 'Category name already exists.')
	);
	render(Home);
	await fireEvent.click(await screen.findByRole('button', { name: 'Kategorie hinzufügen' }));
	const dialog = within(screen.getByRole('dialog', { name: 'Neue Kategorie' }));
	const name = dialog.getByLabelText<HTMLInputElement>('Name');
	await fireEvent.input(name, { target: { value: 'Kuche' } });
	await fireEvent.click(dialog.getByRole('button', { name: 'Anlegen' }));
	expect((await dialog.findByRole('alert')).textContent).toContain(
		'Dieser Kategoriename ist bereits vergeben.'
	);
	expect(name.value).toBe('Kuche');
});

test('a duplicate name is explained during rename without clearing the entry', async () => {
	vi.mocked(api.updateCategory).mockRejectedValueOnce(
		new api.ApiError(409, 'Category name already exists.')
	);
	page.url = new URL('http://localhost/?category=1');
	render(Home);
	await fireEvent.click(await screen.findByRole('button', { name: 'Kategorie umbenennen' }));
	const name = screen.getByLabelText<HTMLInputElement>('Kategoriename');
	await fireEvent.input(name, { target: { value: 'Brot' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
	expect((await screen.findByRole('alert')).textContent).toContain(
		'Dieser Kategoriename ist bereits vergeben.'
	);
	expect(name.value).toBe('Brot');
});

test.each([
	['create', new api.ApiError(500, 'Internal error')],
	['create', new Error('Network error')],
	['rename', new api.ApiError(500, 'Internal error')],
	['rename', new Error('Network error')]
])('%s keeps its action-specific fallback for errors other than name conflicts (%s)', async (action, error) => {
	if (action === 'create') {
		vi.mocked(api.createCategory).mockRejectedValueOnce(error);
	} else {
		vi.mocked(api.updateCategory).mockRejectedValueOnce(error);
		page.url = new URL('http://localhost/?category=1');
	}
	render(Home);
	await fireEvent.click(await screen.findByRole('button', {
		name: action === 'create' ? 'Kategorie hinzufügen' : 'Kategorie umbenennen'
	}));
	await fireEvent.input(screen.getByLabelText(action === 'create' ? 'Name' : 'Kategoriename'), {
		target: { value: 'Backen' }
	});
	await fireEvent.click(screen.getByRole('button', { name: action === 'create' ? 'Anlegen' : 'Speichern' }));
	expect((await screen.findByRole('alert')).textContent).toContain(
		action === 'create' ? 'Kategorie konnte nicht angelegt werden.' : 'Kategorie konnte nicht umbenannt werden.'
	);
});

test('creating a category refreshes the overview and reopening starts an empty form', async () => {
	const created = { ...kitchen, id: 2, name: 'Backen' };
	vi.mocked(api.createCategory).mockResolvedValue(created);
	vi.mocked(api.listCategories).mockResolvedValueOnce([kitchen]).mockResolvedValue([kitchen, created]);
	render(Home);
	await fireEvent.click(await screen.findByRole('button', { name: 'Kategorie hinzufügen' }));
	let dialog = within(screen.getByRole('dialog', { name: 'Neue Kategorie' }));
	await fireEvent.input(dialog.getByLabelText('Name'), { target: { value: 'Backen' } });
	await fireEvent.click(dialog.getByRole('button', { name: 'Anlegen' }));
	expect(await screen.findByRole('link', { name: 'Backen Noch keine Rezepte' })).toBeTruthy();
	await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
	expect(api.createCategory).toHaveBeenCalledExactlyOnceWith({ name: 'Backen' });
	expect(api.listCategories).toHaveBeenCalledTimes(2);
	await fireEvent.click(screen.getByRole('button', { name: 'Kategorie hinzufügen' }));
	dialog = within(screen.getByRole('dialog', { name: 'Neue Kategorie' }));
	expect(dialog.getByLabelText<HTMLInputElement>('Name').value).toBe('');
});

test('renaming refreshes the selected category and returns to its heading', async () => {
	const renamed = { ...kitchen, name: 'Backen' };
	vi.mocked(api.updateCategory).mockResolvedValue(renamed);
	vi.mocked(api.listCategories).mockResolvedValueOnce([kitchen]).mockResolvedValue([renamed]);
	page.url = new URL('http://localhost/?category=1');
	render(Home);
	await fireEvent.click(await screen.findByRole('button', { name: 'Kategorie umbenennen' }));
	await fireEvent.input(screen.getByLabelText('Kategoriename'), { target: { value: 'Backen' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
	expect(await screen.findByRole('heading', { name: 'Backen' })).toBeTruthy();
	expect(screen.queryByLabelText('Kategoriename')).toBeNull();
	expect(api.updateCategory).toHaveBeenCalledExactlyOnceWith(1, { name: 'Backen' });
	expect(api.listCategories).toHaveBeenCalledTimes(2);
	expect(page.url.searchParams.get('category')).toBe('1');
});

test('category deletion can be cancelled, explains occupied categories and returns home after success', async () => {
	vi.mocked(api.deleteCategory)
		.mockRejectedValueOnce(new api.ApiError(409, 'Category has recipes.'))
		.mockResolvedValue(undefined);
	page.url = new URL('http://localhost/?category=1');
	render(Home);
	await fireEvent.click(await screen.findByRole('button', { name: 'Kategorie löschen' }));
	let dialog = within(screen.getByRole('dialog', { name: 'Kategorie löschen?' }));
	await fireEvent.click(dialog.getByRole('button', { name: 'Abbrechen' }));
	expect(api.deleteCategory).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByRole('button', { name: 'Kategorie löschen' }));
	dialog = within(screen.getByRole('dialog', { name: 'Kategorie löschen?' }));
	await fireEvent.click(dialog.getByRole('button', { name: 'Endgültig löschen' }));
	expect((await screen.findByRole('alert')).textContent).toContain('solange ihr Rezepte zugeordnet sind');
	expect(page.url.searchParams.get('category')).toBe('1');
	expect(screen.queryByRole('dialog')).toBeNull();
	vi.mocked(api.listCategories).mockResolvedValue([]);
	await fireEvent.click(screen.getByRole('button', { name: 'Kategorie löschen' }));
	dialog = within(screen.getByRole('dialog', { name: 'Kategorie löschen?' }));
	await fireEvent.click(dialog.getByRole('button', { name: 'Endgültig löschen' }));
	expect(await screen.findByText('Noch keine Kategorien angelegt.')).toBeTruthy();
	expect(api.deleteCategory).toHaveBeenCalledTimes(2);
	expect(api.deleteCategory).toHaveBeenLastCalledWith(1);
	expect(page.url.pathname + page.url.search).toBe('/');
});

test('removing a category image refreshes the editor without closing it', async () => {
	vi.mocked(api.listCategories)
		.mockResolvedValueOnce([{ ...kitchen, image_path: '/kitchen.jpg' }])
		.mockResolvedValue([kitchen]);
	vi.mocked(api.removeCategoryImage).mockResolvedValue(kitchen);
	page.url = new URL('http://localhost/?category=1');
	render(Home);
	await fireEvent.click(await screen.findByRole('button', { name: 'Kategorie umbenennen' }));
	await fireEvent.click(screen.getByRole('button', { name: 'Bild entfernen' }));
	expect(await screen.findByLabelText('Bild hinzufügen')).toBeTruthy();
	expect(screen.queryByRole('button', { name: 'Bild entfernen' })).toBeNull();
	expect(screen.getByLabelText<HTMLInputElement>('Kategoriename').value).toBe('Küche');
	expect(api.removeCategoryImage).toHaveBeenCalledExactlyOnceWith(1);
	expect(api.listCategories).toHaveBeenCalledTimes(2);
});

test('editors can add recipes but cannot manage the selected category', async () => {
	auth.user!.role = 'editor';
	page.url = new URL('http://localhost/?category=1');
	render(Home);
	await screen.findByRole('heading', { name: 'Küche' });
	expect(screen.getByRole('link', { name: 'Rezept' }).getAttribute('href')).toBe('/recipes/new?category=1');
	expect(screen.queryByRole('button', { name: 'Kategorie umbenennen' })).toBeNull();
	expect(screen.queryByRole('button', { name: 'Kategorie löschen' })).toBeNull();
});

test('an admin can use the camera or crop the existing category image and save the replacement', async () => {
	const withImage = { ...kitchen, image_path: '/kitchen.jpg' };
	const cropped = { ...kitchen, image_path: '/cropped.jpg' };
	vi.mocked(api.listCategories).mockResolvedValueOnce([withImage]).mockResolvedValue([cropped]);
	vi.mocked(api.setCategoryImage).mockResolvedValue(cropped);
	const fetchImage = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
		new Response('image', {
			headers: { 'Content-Type': 'image/jpeg' }
		})
	);
	vi.stubGlobal(
		'URL',
		class extends URL {
			static createObjectURL = vi.fn(() => 'blob:category-image');
			static revokeObjectURL = vi.fn();
		}
	);
	page.url = new URL('http://localhost/?category=1');
	render(Home);
	await fireEvent.click(await screen.findByRole('button', { name: 'Kategorie umbenennen' }));
	expect(screen.getByLabelText('Foto aufnehmen').getAttribute('capture')).toBe('environment');
	await fireEvent.click(screen.getByRole('button', { name: 'Bild zuschneiden' }));
	const dialog = within(await screen.findByRole('dialog', { name: 'Bild zuschneiden' }));
	expect(fetchImage).toHaveBeenCalledExactlyOnceWith('/kitchen.jpg');
	await fireEvent.click(dialog.getByRole('button', { name: 'Zuschneiden und speichern' }));
	expect(api.setCategoryImage).toHaveBeenCalledExactlyOnceWith(1, expect.any(File));
	await waitFor(() => expect(document.querySelector('img[src="/cropped.jpg"]')).toBeTruthy());
});

test('an editor sees who must create the first category and cannot submit a recipe yet', async () => {
	auth.user!.role = 'editor';
	vi.mocked(api.listCategories).mockResolvedValue([]);
	page.url = new URL('http://localhost/recipes/new?category=99');
	render(NewRecipe);
	expect(
		await screen.findByText(
			'Es ist noch keine Kategorie vorhanden. Bitte wende dich an einen Administrator.'
		)
	).toBeTruthy();
	const save = screen.getByRole<HTMLButtonElement>('button', { name: 'Rezept speichern' });
	expect(save.disabled).toBe(true);
	await fireEvent.submit(save.form!);
	expect(api.createRecipe).not.toHaveBeenCalled();
});
