import { offline } from '$lib/stores/offline.svelte';
import { beforeEach, expect, test, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/svelte';
import Home from '../../src/routes/+page.svelte';
import Settings from '../../src/routes/admin/settings/+page.svelte';
import Login from '../../src/routes/login/+page.svelte';
import Header from '../../src/lib/components/Header.svelte';
import RecipeFieldsForm from '../../src/lib/components/RecipeFieldsForm.svelte';
import { page } from './navigation.svelte';
import { auth } from '../../src/lib/stores/auth.svelte';
import { cookbook } from '../../src/lib/stores/settings.svelte';
import * as api from '../../src/lib/api';
import type { RecipeInput, RecipeSummary } from '../../src/lib/types';
vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	listRecipes: vi.fn(),
	listCategories: vi.fn(),
	login: vi.fn(),
	resetAvailable: vi.fn(async () => ({ available: false })),
	getViewPreferences: vi.fn(async () => ({
		category_sort: 'manual',
		recipe_view: 'list',
		category_ids: []
	})),
	getSettings: vi.fn(),
	getSmtpSettings: vi.fn().mockRejectedValue(new Error('SMTP unavailable')),
	updateSettings: vi.fn()
}));
const category = {
	id: 1,
	name: 'Familienrezepte',
	recipe_count: 250,
	description: null,
	image_path: null,
	image_alt_text: null
};
const all = Array.from({ length: 250 }, (_, i) => ({
	id: i + 1,
	title: `Rezept ${String(i + 1).padStart(3, '0')}`,
	origin_person: 'Oma',
	preparation_days: 1,
	images: [],
	category
}));
beforeEach(() => {
	page.params = { id: '1' };
	page.state = {};
	page.url = new URL('http://localhost/');
	localStorage.clear();
	auth.user = null;
	auth.loading = false;
	auth.initialized = true;
	vi.mocked(api.listCategories).mockResolvedValue([category]);
	vi.mocked(api.listRecipes).mockImplementation(
		async ({ page = 1, page_size = 20, sort }) =>
			({
				total: 250,
				page,
				page_size,
				items: (sort === 'newest' ? [...all].reverse() : all).slice(
					(page - 1) * page_size,
					page * page_size
				)
			}) as never
	);
});
test('contents uses database count and three newest recipes; category pagination reaches all 250', async () => {
	render(Home);
	const link = await screen.findByRole('link', { name: 'Familienrezepte 250 Rezepte' });
	expect(link.getAttribute('href')).toBe('/?category=1');
	await screen.findByRole('link', { name: /Rezept 250/ });
	expect(screen.getAllByRole('link', { name: /Rezept \d/ })).toHaveLength(3);
	page.url = new URL('http://localhost/?category=1');
	await screen.findByRole('link', { name: /Rezept 001/ });
	expect(screen.getByText('250 Rezepte')).toBeTruthy();
	for (let i = 1; i < 13; i++) {
		await fireEvent.click(screen.getByRole('button', { name: /Weitere Rezepte laden/ }));
		await waitFor(() =>
			expect(screen.getAllByRole('link', { name: /Rezept \d/ })).toHaveLength(
				Math.min((i + 1) * 20, 250)
			)
		);
	}
	expect(screen.getByRole('link', { name: /Rezept 250/ })).toBeTruthy();
	expect(screen.queryByRole('button', { name: /Weitere Rezepte laden/ })).toBeNull();
	expect(document.querySelector('.recipe-grid.list')).toBeTruthy();
	expect(screen.queryByRole('button', { name: 'Kategorie löschen' })).toBeNull();
});
test('the view toggle switches the guest recipe layout and keeps the browser preference', async () => {
	page.url = new URL('http://localhost/?category=1');
	render(Home);
	await screen.findByRole('link', { name: /Rezept 001/ });
	expect(screen.getByRole('button', { name: 'Listenansicht', pressed: true })).toBeTruthy();
	await fireEvent.click(screen.getByRole('button', { name: 'Kachelansicht' }));
	expect(screen.getByRole('button', { name: 'Kachelansicht', pressed: true })).toBeTruthy();
	expect(document.querySelector('.recipe-grid.list')).toBeNull();
	expect(localStorage.getItem('heritagekitchen:recipe-view')).toBe('grid');
	await fireEvent.click(screen.getByRole('button', { name: 'Listenansicht' }));
	expect(screen.getByRole('button', { name: 'Listenansicht', pressed: true })).toBeTruthy();
	expect(document.querySelector('.recipe-grid.list')).toBeTruthy();
	expect(localStorage.getItem('heritagekitchen:recipe-view')).toBe('list');
});

test('empty category uses the same count on the home page and in the category', async () => {
	vi.mocked(api.listCategories).mockResolvedValue([
		{ ...category, recipe_count: null },
		{ ...category, id: 2, name: 'Brot', recipe_count: 1 }
	]);
	vi.mocked(api.listRecipes).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
	render(Home);
	await screen.findByRole('link', { name: 'Familienrezepte Noch keine Rezepte' });
	expect(screen.getByRole('link', { name: 'Brot 1 Rezept' })).toBeTruthy();

	page.url = new URL('http://localhost/?category=1');
	await screen.findByText('In dieser Kategorie gibt es noch keine Rezepte.');
	expect(screen.getByText('Noch keine Rezepte')).toBeTruthy();
	expect(screen.queryByRole('link', { name: 'Rezept hinzufügen' })).toBeNull();
});
test('recent recipes show a cover or placeholder and only available metadata', async () => {
	const bare: RecipeSummary = {
		id: 1,
		version: 1,
		title: 'Einfaches Brot',
		summary: null,
		origin_person: ' ',
		preparation_days: 1,
		preparation_time: null,
		cooking_time: null,
		cooking_time_max: null,
		rest_time: null,
		rest_time_max: null,
		servings: null,
		created_at: '',
		updated_at: '',
		images: [],
		category: null,
		category_id: null
	};
	const withPhoto: RecipeSummary = {
		...bare,
		id: 2,
		title: 'Grillbrote',
		origin_person: 'Baking Passion · Seite 107',
		category: { ...category, name: 'Grillen' },
		category_id: category.id,
		preparation_time: 10,
		rest_time: 1020,
		images: [
			{ id: 1, recipe_id: 2, file_path: '/media/brot.jpg', alt_text: 'Grillbrot', is_main: true }
		]
	};
	const items = [
		withPhoto,
		bare,
		{ ...bare, id: 3, title: 'Ohne Kategorie', preparation_days: 2 },
		{ ...bare, id: 4, title: 'Ohne Dauer', category, category_id: category.id }
	];
	vi.mocked(api.listRecipes).mockResolvedValue({
		items,
		total: items.length,
		page: 1,
		page_size: 3
	});

	render(Home);
	const recent = within(await screen.findByRole('region', { name: 'Zuletzt eingetragen' }));
	const fullCard = within(await recent.findByRole('link', { name: /Grillbrote/ }));
	expect(fullCard.getByRole('img', { name: 'Grillbrot' }).getAttribute('src')).toBe(
		'/media/brot.jpg'
	);
	expect(fullCard.getByText('Baking Passion · Seite 107')).toBeTruthy();
	expect(fullCard.getByText('Grillen · 17 Std. 10 Min.')).toBeTruthy();
	const bareCard = recent.getByRole('link', { name: 'Einfaches Brot' });
	expect(bareCard.querySelector('svg[aria-hidden="true"]')).toBeTruthy();
	expect(bareCard.querySelector('p')).toBeNull();
	expect(recent.getByRole('link', { name: 'Ohne Kategorie 2 Tage' })).toBeTruthy();
	expect(recent.getByRole('link', { name: 'Ohne Dauer Familienrezepte' })).toBeTruthy();
});
test('search pagination is not capped and stale category responses cannot replace newer search results', async () => {
	page.url = new URL('http://localhost/?category=1');
	let resolveOld: (value: unknown) => void = () => {};
	vi.mocked(api.listRecipes).mockImplementation(async (params) => {
		if (params.sort === 'newest') return { items: [], total: 0, page: 1, page_size: 3 };
		if (!params.search)
			return new Promise((resolve) => {
				resolveOld = resolve;
			});
		return {
			items: all.slice(((params.page ?? 1) - 1) * 20, (params.page ?? 1) * 20),
			total: 250,
			page: params.page ?? 1,
			page_size: 20
		};
	});
	render(Home);
	await waitFor(() =>
		expect(api.listRecipes).toHaveBeenCalledWith(expect.objectContaining({ category_id: 1 }))
	);
	await fireEvent.input(screen.getByLabelText('Suche'), { target: { value: 'Brot' } });
	await screen.findByRole('link', { name: /Rezept 001/ });
	resolveOld({
		items: [{ ...all[0], title: 'Veralteter Treffer' }],
		total: 1,
		page: 1,
		page_size: 20
	});
	await fireEvent.click(screen.getByRole('button', { name: /Weitere Rezepte laden/ }));
	await screen.findByRole('link', { name: /Rezept 040/ });
	expect(screen.queryByText('Veralteter Treffer')).toBeNull();
	expect(api.listRecipes).toHaveBeenCalledWith(
		expect.objectContaining({ search: 'Brot', page: 2 })
	);
});
test('recipe search distinguishes no matches from a failed request', async () => {
	vi.mocked(api.listRecipes).mockImplementation(async ({ search, page = 1, page_size = 20 }) => {
		if (search === 'Grill') throw new api.ApiError(500, 'Internal Server Error');
		return { items: [], total: 0, page, page_size };
	});
	render(Home);
	const searchField = screen.getByLabelText('Suche');
	await fireEvent.input(searchField, { target: { value: 'Pasta' } });
	await screen.findByText('Keine Rezepte zu deiner Suche gefunden.');
	expect(screen.queryByText('Rezepte konnten nicht geladen werden.')).toBeNull();
	await fireEvent.input(searchField, { target: { value: 'Grill' } });
	await screen.findByText('Rezepte konnten nicht geladen werden.');
	expect(screen.queryByText('Keine Rezepte zu deiner Suche gefunden.')).toBeNull();
});

test.each(['/login', '/login?redirectTo=/favorites'])(
	'login from %s returns to the same category overview with account actions',
	async (loginUrl) => {
		const guestHome = render(Home);
		const { unmount: unmountHeader } = render(Header);
		const categoryLink = 'Familienrezepte 250 Rezepte';
		const guestCategories = await screen.findAllByRole('link', { name: /\d+ Rezepte$/ });
		const guestCategoryLinks = guestCategories.map((link) => link.getAttribute('href'));
		expect((await screen.findByRole('link', { name: categoryLink })).getAttribute('href')).toBe(
			'/?category=1'
		);
		expect(screen.queryByRole('link', { name: 'Meine Favoriten' })).toBeNull();
		guestHome.unmount();
		unmountHeader();

		page.url = new URL(loginUrl, page.url);
		const reader = {
			id: 1,
			username: 'reader',
			email: null,
			email_verified_at: null,
			role: 'reader',
			is_active: true,
			pending_approval: false,
			created_at: ''
		} as const;
		vi.mocked(api.login).mockResolvedValue(reader);
		const login = render(Login);
		await fireEvent.input(screen.getByLabelText('Benutzername'), {
			target: { value: 'reader' }
		});
		await fireEvent.input(screen.getByLabelText('Passwort'), { target: { value: 'supersecret123' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Anmelden' }));
		await waitFor(() => expect(page.url.href).toBe('http://localhost/'));
		login.unmount();

		render(Header);
		render(Home);
		const link = await screen.findByRole('link', { name: categoryLink });
		expect(link.getAttribute('href')).toBe('/?category=1');
		expect(
			screen.getAllByRole('link', { name: /\d+ Rezepte$/ }).map((item) => item.getAttribute('href'))
		).toEqual(guestCategoryLinks);
		expect(screen.getByRole('link', { name: 'Meine Favoriten' })).toBeTruthy();
		expect(screen.queryByRole('link', { name: 'Neues Rezept' })).toBeNull();
	}
);

test('settings save cookbook identity without a read access switch', async () => {
	auth.user = {
		id: 1,
		username: 'admin',
		email: null,
		email_verified_at: null,
		role: 'admin',
		is_active: true,
		pending_approval: false,
		created_at: ''
	};
	vi.mocked(api.getSettings).mockResolvedValue({
		cookbook_name: 'Heritage Kitchen',
		home_title: 'Lieblingsrezepte',
		home_tagline: 'Unsere Rezepte.',
		footer_text: 'Mit Liebe gesammelt',
	});
	vi.mocked(api.updateSettings).mockImplementation(async (settings) => settings as never);
	render(Settings);
	await fireEvent.input(await screen.findByLabelText('Name des Kochbuchs'), {
		target: { value: ' Unsere Familienküche ' }
	});
	await fireEvent.input(screen.getByLabelText('Überschrift der Startseite'), {
		target: { value: 'Unser Kochbuch' }
	});
	expect(screen.queryByLabelText('Lesen nur mit Anmeldung')).toBeNull();
	expect((screen.getByLabelText('Footertext') as HTMLInputElement).value).toBe('Mit Liebe gesammelt');
	await fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
	await screen.findByText('Einstellungen gespeichert.');
	expect(screen.queryByRole('heading', { name: 'Datenbank' })).toBeNull();
	expect(api.updateSettings).toHaveBeenCalledWith({
		cookbook_name: 'Unsere Familienküche',
		home_title: 'Unser Kochbuch',
		home_tagline: 'Unsere Rezepte.',
		footer_text: 'Mit Liebe gesammelt',
	});
	expect(cookbook.settings.cookbook_name).toBe('Unsere Familienküche');
	expect((screen.getByLabelText('Name des Kochbuchs') as HTMLInputElement).maxLength).toBe(100);
});
test('recipe form offers history, day bounds and editable day suggestions', async () => {
	const form: RecipeInput = {
		title: 'Brot',
		summary: null,
		history: 'Sonntags',
		origin_person: 'Oma',
		preparation_days: 3,
		preparation_time: null,
		rest_time: null,
		rest_time_max: null,
		cooking_time: null,
		cooking_time_max: null,
		servings: null,
		important_notes: null,
		notes: null,
		category_id: 1,
		ingredient_groups: [],
		ingredients: [],
		steps: [{ position: 0, heading: '', instruction: 'Mischen', note: null, is_important: false }]
	};
	render(RecipeFieldsForm, { form, categories: [category] });
	expect(screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent)).toEqual([
		'Grunddaten',
		'Zutaten',
		'Zubereitung'
	]);
	expect(screen.queryByRole('heading', { name: /Verknüpfte Rezepte|Varianten|Backform/ })).toBeNull();
	expect(screen.queryByRole('button', { name: 'Rezepte suchen' })).toBeNull();
	const tinInstruction = 'Für die 20-cm-Form 350 g Mehl verwenden.';
	const instruction = screen.getByPlaceholderText('Anweisung *') as HTMLTextAreaElement;
	await fireEvent.input(instruction, { target: { value: tinInstruction } });
	expect(instruction.value).toBe(tinInstruction);

	await fireEvent.click(screen.getByRole('button', { name: /Mehr Details/ }));
	expect((screen.getByLabelText('Geschichte zum Rezept') as HTMLTextAreaElement).maxLength).toBe(
		5000
	);
	const days = screen.getByLabelText('Verteilt über … Tage') as HTMLInputElement;
	expect(days.min).toBe('1');
	expect(days.max).toBe('14');
	expect(
		[...document.querySelectorAll('#recipe-days option')].map((option) =>
			option.getAttribute('value')
		)
	).toEqual(['Tag 1', 'Tag 2', 'Tag 3']);
	expect(document.querySelector('input[list="recipe-days"]')).toBeTruthy();
});

test('a new offline generation refreshes the open category and recent recipes', async () => {
	page.url = new URL('http://localhost/?category=1');
	render(Home);
	await screen.findByRole('link', { name: /Rezept 001/ });
	vi.mocked(api.listRecipes).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
	try {
		offline.generation = 'new-home-generation';
		await screen.findByText('In dieser Kategorie gibt es noch keine Rezepte.');
		expect(screen.queryByRole('link', { name: /Rezept 001/ })).toBeNull();
	} finally {
		offline.generation = null;
	}
});
