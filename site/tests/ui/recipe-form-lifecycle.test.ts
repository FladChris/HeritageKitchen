import { beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import NewRecipePage from '../../src/routes/recipes/new/+page.svelte';
import EditRecipePage from '../../src/routes/recipes/[id]/edit/+page.svelte';
import { navigateAllowed, page } from './navigation.svelte';
import { auth } from '../../src/lib/stores/auth.svelte';
import * as api from '../../src/lib/api';
import type { Recipe } from '../../src/lib/types';

vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	listCategories: vi.fn(),
	getRecipe: vi.fn(),
	createRecipe: vi.fn(),
	updateRecipe: vi.fn(),
	deleteRecipe: vi.fn(),
	deleteRecipeImage: vi.fn()
}));

const category = {
	id: 1,
	name: 'Backen',
	recipe_count: 1,
	description: null,
	image_path: null,
	image_alt_text: null
};

const recipe: Recipe = {
	id: 7,
	version: 1,
	title: 'Omas Apfelkuchen',
	category_id: 1,
	category,
	created_at: '',
	updated_at: '',
	summary: null,
	preparation_time: null,
	cooking_time: null,
	cooking_time_max: null,
	rest_time: null,
	rest_time_max: null,
	servings: null,
	origin_person: null,
	history: null,
	preparation_days: 1,
	day_titles: null,
	notes: null,
	important_notes: null,
	ingredients: [],
	ingredient_groups: [],
	steps: [],
	images: []
};

beforeEach(() => {
	vi.clearAllMocks();
	page.params = { id: '7' };
	page.state = {};
	page.url = new URL('http://localhost/recipes/new');
	auth.user = {
		id: 2, username: 'Lena', email_verified_at: null, email: null,
		role: 'editor', is_active: true, pending_approval: false, created_at: ''
	};
	auth.initialized = true;
	auth.loading = false;
	vi.mocked(api.listCategories).mockResolvedValue([category]);
	vi.mocked(api.getRecipe).mockResolvedValue(structuredClone(recipe));
	vi.mocked(api.createRecipe).mockResolvedValue(structuredClone(recipe));
	vi.mocked(api.updateRecipe).mockResolvedValue(structuredClone(recipe));
	vi.mocked(api.deleteRecipe).mockResolvedValue(undefined);
});

test.each(['new', 'edit'])('%s recipe guards only unsaved changes and leaves browser unload confirmation to the browser', async (mode) => {
	page.url = new URL(`http://localhost/recipes/${mode === 'new' ? 'new' : '7/edit'}`);
	const { unmount } = render(mode === 'new' ? NewRecipePage : EditRecipePage);
	await screen.findByRole('option', { name: 'Backen' });
	const title = screen.getByLabelText<HTMLInputElement>('Titel *');
	const initialTitle = title.value;
	const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
	expect(navigateAllowed()).toBe(true);
	expect(navigateAllowed(true)).toBe(true);
	await fireEvent.input(title, { target: { value: 'Ungespeichert' } });
	expect(navigateAllowed(true)).toBe(false);
	expect(confirm).not.toHaveBeenCalled();
	expect(navigateAllowed()).toBe(false);
	expect(confirm).toHaveBeenCalledWith('Ungespeicherte Änderungen verwerfen?');
	await fireEvent.input(title, { target: { value: initialTitle } });
	confirm.mockClear();
	expect(navigateAllowed()).toBe(true);
	expect(confirm).not.toHaveBeenCalled();
	await fireEvent.input(title, { target: { value: 'Ungespeichert' } });
	unmount();
	expect(navigateAllowed()).toBe(true);
});

test('new recipe warns on discard and returns to detail on explicit save', async () => {
	render(NewRecipePage);
	await screen.findByRole('option', { name: 'Backen' });
	await fireEvent.input(screen.getByLabelText('Titel *'), { target: { value: 'Mein Brot' } });
	await fireEvent.change(screen.getByLabelText('Kategorie *'), { target: { value: '1' } });
	const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
	expect(navigateAllowed()).toBe(false);
	expect(confirm).toHaveBeenCalledWith('Ungespeicherte Änderungen verwerfen?');
	expect((screen.getByLabelText('Titel *') as HTMLInputElement).value).toBe('Mein Brot');
	confirm.mockReturnValue(true);
	expect(navigateAllowed()).toBe(true);
	confirm.mockClear();
	confirm.mockReturnValue(false);
	await fireEvent.click(screen.getByRole('button', { name: 'Rezept speichern' }));
	await waitFor(() => expect(api.createRecipe).toHaveBeenCalledWith(
		expect.objectContaining({ title: 'Mein Brot', category_id: 1, ingredients: [], steps: [] })
	));
	await waitFor(() => expect(page.url.pathname + page.url.search).toBe('/recipes/7?saved=created'));
	expect(confirm).not.toHaveBeenCalled();
});

test('editing grouped ingredients preserves their order and saves changes from the ingredient editor', async () => {
	page.url = new URL('http://localhost/recipes/7/edit');
	vi.mocked(api.getRecipe).mockResolvedValue({
		...structuredClone(recipe),
		ingredient_groups: [{ id: 1, recipe_id: 7, position: 0, name: 'Teig' }],
		ingredients: [
			{ id: 2, recipe_id: 7, position: 1, group_position: 0, name: 'Mehl', amount: '250', unit: 'g', note: null },
			{ id: 1, recipe_id: 7, position: 0, group_position: null, name: 'Salz', amount: null, unit: 'Prise', note: null }
		]
	});
	render(EditRecipePage);
	await screen.findByDisplayValue('Mehl');
	expect(screen.getAllByRole<HTMLInputElement>('textbox', { name: 'Zutat', exact: true }).map((input) => input.value))
		.toEqual(['Salz', 'Mehl']);
	await fireEvent.input(screen.getByRole('textbox', { name: 'Überschrift', exact: true }), { target: { value: 'Hauptteig' } });
	await fireEvent.input(screen.getByDisplayValue('250'), { target: { value: '300' } });
	const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
	expect(navigateAllowed()).toBe(false);
	expect(confirm).toHaveBeenCalled();
	await fireEvent.click(screen.getByRole('button', { name: 'Änderungen speichern' }));
	expect(api.updateRecipe).toHaveBeenCalledWith(7, expect.objectContaining({
		ingredient_groups: [{ position: 0, name: 'Hauptteig' }],
		ingredients: [
			expect.objectContaining({ position: 0, group_position: null, name: 'Salz' }),
			expect.objectContaining({ position: 1, group_position: 0, name: 'Mehl', amount: '300' })
		]
	}), 1);
});

test('bulk ingredient groups and reordering reach the new recipe payload', async () => {
	render(NewRecipePage);
	await screen.findByRole('option', { name: 'Backen' });
	await fireEvent.input(screen.getByLabelText('Titel *'), { target: { value: 'Kuchen' } });
	await fireEvent.change(screen.getByLabelText('Kategorie *'), { target: { value: '1' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Mehrere Zutaten einfügen' }));
	await fireEvent.input(screen.getByLabelText('Mehrere Zutaten einfügen'), {
		target: { value: 'Teig:\n200 g Mehl\n100 g Zucker' }
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Vorschau' }));
	await fireEvent.click(screen.getByRole('button', { name: 'Übernehmen' }));
	await fireEvent.click(screen.getAllByRole('button', { name: 'Zutat nach oben verschieben' })[1]);
	await fireEvent.click(screen.getByRole('button', { name: 'Rezept speichern' }));
	expect(api.createRecipe).toHaveBeenCalledWith(expect.objectContaining({
		ingredient_groups: [{ position: 0, name: 'Teig' }],
		ingredients: [
			expect.objectContaining({ position: 0, group_position: 0, name: 'Zucker', amount: '100', unit: 'g' }),
			expect.objectContaining({ position: 1, group_position: 0, name: 'Mehl', amount: '200', unit: 'g' })
		]
	}));
});

test('ingredient removal can be cancelled and confirmed without removing preparation steps', async () => {
	render(NewRecipePage);
	await screen.findByRole('option', { name: 'Backen' });
	await fireEvent.click(screen.getByRole('button', { name: 'Zutat', exact: true }));
	await fireEvent.input(screen.getByRole('textbox', { name: 'Zutat', exact: true }), { target: { value: 'Mehl' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Schritt', exact: true }));
	await fireEvent.click(screen.getByRole('button', { name: 'Zutat entfernen' }));
	let dialog = screen.getByRole('dialog', { name: 'Zutat entfernen?' });
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Abbrechen' }));
	expect(screen.getByDisplayValue('Mehl')).toBeTruthy();
	await fireEvent.click(screen.getByRole('button', { name: 'Zutat entfernen' }));
	dialog = screen.getByRole('dialog', { name: 'Zutat entfernen?' });
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Entfernen' }));
	expect(screen.queryByDisplayValue('Mehl')).toBeNull();
	expect(screen.getByRole('button', { name: 'Schritt entfernen' })).toBeTruthy();
});

test('creating a recipe with overridden manual times requests the notice', async () => {
	vi.mocked(api.createRecipe).mockResolvedValue({
		...recipe,
		cooking_time: 45,
		steps: [{
			id: 1, recipe_id: recipe.id, position: 0, instruction: 'Backen', heading: null,
			note: null, is_important: false, duration_minutes: 35, time_kind: 'cooking', day: 1
		}]
	});
	render(NewRecipePage);
	await screen.findByRole('option', { name: 'Backen' });
	await fireEvent.input(screen.getByLabelText('Titel *'), { target: { value: recipe.title } });
	await fireEvent.change(screen.getByLabelText('Kategorie *'), { target: { value: '1' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Rezept speichern' }));
	await waitFor(() => expect(page.url.searchParams.get('timenotice')).toBe('1'));
	expect(page.url.searchParams.get('saved')).toBe('created');
});

test('more than 14 preparation days blocks saving until the value is corrected', async () => {
	render(NewRecipePage);
	await screen.findByRole('option', { name: 'Backen' });
	await fireEvent.input(screen.getByLabelText('Titel *'), { target: { value: recipe.title } });
	await fireEvent.change(screen.getByLabelText('Kategorie *'), { target: { value: '1' } });
	await fireEvent.click(screen.getByRole('button', { name: /Mehr Details/ }));
	const days = screen.getByRole<HTMLInputElement>('spinbutton', { name: 'Verteilt über … Tage' });
	await fireEvent.change(days, { target: { value: '15' } });
	const error = screen.getByRole('alert');
	expect(error.textContent).toBe('Ein Rezept darf höchstens 14 Zubereitungstage umfassen.');
	expect(days.value).toBe('15');
	expect(days.getAttribute('aria-describedby')).toBe(error.id);
	await fireEvent.submit(days.form!);
	expect(api.createRecipe).not.toHaveBeenCalled();
	await fireEvent.input(days, { target: { value: '14' } });
	await fireEvent.change(days);
	expect(screen.queryByRole('alert')).toBeNull();
	await fireEvent.click(screen.getByRole('button', { name: 'Rezept speichern' }));
	expect(api.createRecipe).toHaveBeenCalledWith(expect.objectContaining({ preparation_days: 14 }));
});

test('required recipe fields expose invalid state and text errors for assistive tech', async () => {
	 render(NewRecipePage);
	 await screen.findByRole('option', { name: 'Backen' });
	 const title = screen.getByRole('textbox', { name: 'Titel *' });
	 await fireEvent.invalid(title);
	 const titleError = screen.getByRole('alert', { name: '' });
	 expect(titleError.textContent).toContain('Bitte einen Titel angeben.');
	 expect(title.getAttribute('aria-invalid')).toBe('true');
	 expect(title.getAttribute('aria-describedby')).toBe(titleError.id);
	 await fireEvent.input(title, { target: { value: 'Apfelkuchen' } });
	 expect(title.getAttribute('aria-invalid')).toBeNull();
	 const category = screen.getByRole('combobox', { name: 'Kategorie *' });
	 await fireEvent.invalid(category);
	 const categoryError = screen.getByRole('alert');
	 expect(categoryError.textContent).toContain('Bitte wähle eine Kategorie aus.');
	 expect(category.getAttribute('aria-describedby')).toBe(categoryError.id);
	 await fireEvent.change(category, { target: { value: '1' } });
	 expect(category.getAttribute('aria-invalid')).toBeNull();
});

test('edit keeps the draft after a deleted-on-server error and confirms final deletion', async () => {
	page.url = new URL('http://localhost/recipes/7/edit');
	render(EditRecipePage);
	await screen.findByDisplayValue('Omas Apfelkuchen');
	await fireEvent.input(screen.getByLabelText('Titel *'), { target: { value: 'Geändertes Rezept' } });
	const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
	expect(navigateAllowed()).toBe(false);
	expect(navigateAllowed(true)).toBe(false); // Browser uses its own beforeunload confirmation.
	vi.mocked(api.updateRecipe).mockRejectedValueOnce(new api.ApiError(404, 'Rezept nicht gefunden.'));
	await fireEvent.click(screen.getByRole('button', { name: 'Änderungen speichern' }));
	await screen.findByText(/Dieses Rezept wurde inzwischen gelöscht/);
	expect((screen.getByLabelText('Titel *') as HTMLInputElement).value).toBe('Geändertes Rezept');

	await fireEvent.click(screen.getByRole('button', { name: 'Rezept löschen' }));
	await screen.findByText(/einschließlich aller Bilder, Kommentare, Bewertungen und Favoriten/);
	expect(api.deleteRecipe).not.toHaveBeenCalled();
	const buttons = screen.getAllByRole('button', { name: 'Rezept löschen' });
	await fireEvent.click(buttons[buttons.length - 1]);
	await waitFor(() => expect(api.deleteRecipe).toHaveBeenCalledWith(7));
	await waitFor(() => expect(page.url.pathname + page.url.search).toBe('/?deleted=1&category=1'));
});

async function deleteImageOnEditPage(versionHeaders: [number, number]) {
	page.url = new URL('http://localhost/recipes/7/edit');
	vi.mocked(api.getRecipe).mockResolvedValue({
		...structuredClone(recipe),
		images: [{ id: 5, recipe_id: 7, file_path: '/media/5.jpg', alt_text: null, is_main: true }]
	});
	vi.mocked(api.deleteRecipeImage).mockImplementation(async (_id, expectedVersion) => {
		if (expectedVersion !== versionHeaders[0]) throw new api.ApiError(409, 'Conflict', {
			code: 'recipe_version_conflict', current_version: versionHeaders[0]
		});
		api.reportRecipeVersion(...versionHeaders);
	});
	render(EditRecipePage);
	await screen.findByDisplayValue('Omas Apfelkuchen');
	await fireEvent.click(screen.getByRole('button', { name: 'Bild 1 entfernen' }));
	const dialog = await screen.findByRole('dialog', { name: 'Bild entfernen?' });
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Entfernen' }));
	await waitFor(() => expect(api.deleteRecipeImage).toHaveBeenCalledWith(5, 1));
	await fireEvent.click(screen.getByRole('button', { name: 'Änderungen speichern' }));
}

test('own image change advances the base version so the following save does not conflict', async () => {
	await deleteImageOnEditPage([1, 2]);
	await waitFor(() => expect(api.updateRecipe).toHaveBeenCalledWith(7, expect.anything(), 2));
});

test('a stale image change surfaces the conflict and keeps the old base version', async () => {
	await deleteImageOnEditPage([2, 3]);
	expect(screen.getByText(/Rezept wurde inzwischen geändert/)).toBeTruthy();
	await waitFor(() => expect(api.updateRecipe).toHaveBeenCalledWith(7, expect.anything(), 1));
});

test.each([
	{ Page: NewRecipePage, save: 'Rezept speichern', persist: api.createRecipe },
	{ Page: EditRecipePage, save: 'Änderungen speichern', persist: api.updateRecipe }
])('submitting a whitespace title shows a field error before $save', async ({ Page, save, persist }) => {
	render(Page);
	await screen.findByRole('option', { name: 'Backen' });
	await fireEvent.change(screen.getByLabelText('Kategorie *'), { target: { value: '1' } });
	const title = screen.getByRole<HTMLInputElement>('textbox', { name: 'Titel *' });
	// Autofill or a preloaded field can reach submit without dispatching an input event.
	title.value = '   ';
	await fireEvent.click(screen.getByRole('button', { name: save }));
	const alert = await screen.findByText('Bitte einen Titel angeben.');
	expect(alert.getAttribute('role')).toBe('alert');
	expect(title.getAttribute('aria-invalid')).toBe('true');
	expect(title.getAttribute('aria-describedby')).toBe(alert.id);
	expect(title.validity.customError).toBe(true);
	expect(document.activeElement).toBe(title);
	expect(persist).not.toHaveBeenCalled();
	await fireEvent.input(title, { target: { value: 'Brot' } });
	expect(title.validity.customError).toBe(false);
	expect(title.getAttribute('aria-invalid')).toBeNull();
});

test('a server conflict returns focus to the edit submit button after Escape cancel', async () => {
	vi.mocked(api.updateRecipe).mockRejectedValueOnce(new api.ApiError(409, 'Versionskonflikt', {
		code: 'recipe_version_conflict',
		expected_version: 1,
		current_version: 2,
		current: { ...recipe, title: 'Neuer Stand', version: 2 }
	}));
	render(EditRecipePage);
	await screen.findByDisplayValue(recipe.title);
	const save = screen.getByRole('button', { name: 'Änderungen speichern' });
	save.focus();
	await fireEvent.click(save);
	const dialog = await screen.findByRole('dialog', { name: /zwischenzeitlich geändert/ });
	expect(dialog.contains(document.activeElement)).toBe(true);
	await fireEvent(dialog, new Event('cancel', { cancelable: true }));
	expect(screen.queryByRole('dialog')).toBeNull();
	expect(document.activeElement).toBe(save);
});
