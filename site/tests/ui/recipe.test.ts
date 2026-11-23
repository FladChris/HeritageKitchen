import { cookbook, defaultSettings } from '$lib/stores/settings.svelte';
import { offline } from '$lib/stores/offline.svelte';
import { beforeEach, expect, test, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/svelte';
import RecipePage from '../../src/routes/recipes/[id]/+page.svelte';
import RecipeFieldsForm from '../../src/lib/components/RecipeFieldsForm.svelte';
import RecipeVersionHistory from '../../src/lib/components/RecipeVersionHistory.svelte';
import RecipeCard from '../../src/lib/components/RecipeCard.svelte';
import PhotoViewer from '../../src/lib/components/PhotoViewer.svelte';
import TimeField from '../../src/lib/components/TimeField.svelte';
import { page } from './navigation.svelte';
import { auth } from '../../src/lib/stores/auth.svelte';
import * as api from '../../src/lib/api';
import type { Recipe, RecipeVersion } from '../../src/lib/types';
vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	getRecipe: vi.fn(),
	listCategories: vi.fn(),
	listRecipeComments: vi.fn(async () => []),
	getRecipeRatings: vi.fn(async () => ({ average: null, count: 0, ratings: [] })),
	listFavorites: vi.fn(async () => []),
	addFavorite: vi.fn(async () => ({ id: 99 })),
	removeFavorite: vi.fn(async () => {})
}));
const recipe: Recipe = {
	id: 1,
	version: 2,
	title: 'Omas Brot',
	day_titles: null,
	history: 'Jeden Sonntag.\nFür alle.',
	origin_person: 'Oma',
	summary: 'Mit Vorteig',
	preparation_days: 2,
	preparation_time: 20,
	rest_time: 1440,
	rest_time_max: 2880,
	cooking_time: 45,
	cooking_time_max: null,
	servings: 4,
	notes: 'Abkühlen lassen.',
	important_notes: 'Enthält Gluten.',
	category_id: 1,
	category: {
		id: 1,
		name: 'Brot',
		recipe_count: 250,
		description: null,
		image_path: null,
		image_alt_text: null
	},
	created_at: '',
	updated_at: '',
	images: [],
	ingredient_groups: [{ id: 1, recipe_id: 1, position: 0, name: 'Teig' }],
	ingredients: [
		{
			id: 1,
			recipe_id: 1,
			position: 0,
			group_position: 0,
			name: 'Mehl',
			amount: '500',
			unit: 'g',
			note: null
		}
	],
	steps: [
		{
			id: 1,
			recipe_id: 1,
			position: 0,
			heading: 'Tag 1 – am Vorabend',
			instruction: 'Vorteig mischen.',
			is_important: false,
			note: null,
			duration_minutes: null,
			time_kind: null,
			day: 1
		},
		{
			id: 2,
			recipe_id: 1,
			position: 1,
			heading: 'Tag 2',
			instruction: 'Für die 20-cm-Form 350 g Mehl verwenden.',
			is_important: false,
			note: null,
			duration_minutes: null,
			time_kind: null,
			day: 2
		}
	]
};
beforeEach(() => {
	cookbook.settings = defaultSettings;
	page.params = { id: '1' };
	page.state = {};
	page.url = new URL('http://localhost/recipes/1');
	auth.user = null;
	auth.loading = false;
	auth.initialized = true;
	vi.mocked(api.getRecipe).mockImplementation(async (id) =>
		structuredClone(
			id === 1
				? recipe
				: {
						...recipe,
						id,
						title: 'Kleine Form',
						servings: 2,
						preparation_days: 1,
						ingredients: [{ ...recipe.ingredients[0], amount: '250' }],
						steps: []
					}
		)
	);
	vi.spyOn(history, 'back').mockImplementation(() => {
		page.state = {};
	});
	Object.defineProperty(navigator, 'share', { configurable: true, value: undefined });
	Object.defineProperty(navigator, 'wakeLock', { configurable: true, value: undefined });
});
test.each([
	['/favorites', '/favorites'],
	['/?category=2', '/?category=2'],
	['/?search=Äpfel%20%26%20Brot', '/?search=Äpfel%20%26%20Brot'],
	['/?category=2&search=Brot', '/?category=2&search=Brot'],
	['//example.com/', '/?category=1'],
	[null, '/?category=1']
])('returns from recipe detail to its overview (%s)', async (overview, expected) => {
	page.url = new URL('http://localhost/recipes/1');
	if (overview) page.url.searchParams.set('returnTo', overview);
	render(RecipePage);
	await screen.findByRole('heading', { name: 'Omas Brot' });
	expect(document.querySelector('a.back-link')?.getAttribute('href')).toBe(expected);
});

test('recipes show their own quantities and tin instructions without variant navigation', async () => {
	render(RecipePage);
	await screen.findByRole('heading', { name: 'Omas Brot' });
	expect(screen.queryByRole('button', { name: 'Versionsverlauf' })).toBeNull();
	expect(screen.getByText(/Über 2 Tage/).textContent).toBe(
		'Über 2 Tage · 20 Min. Arbeit · 1–2 Tage Ruhezeit · 45 Min. Koch-/Backzeit · Summe der erfassten Zeiten: 1 Tag 1 Std. 5 Min. bis 2 Tage 1 Std. 5 Min. · Für 4 Portionen'
	);
	expect(screen.getByText(/Jeden Sonntag/).textContent).toBe('Jeden Sonntag.\nFür alle.');
	const notice = screen.getByRole('heading', { name: 'Wichtiger Hinweis' });
	expect(
		notice.compareDocumentPosition(screen.getByRole('heading', { name: 'Zutaten' })) &
			Node.DOCUMENT_POSITION_FOLLOWING
	).toBeTruthy();
	expect(document.querySelector('.gallery')).toBeNull();
	expect(screen.queryByText('Bearbeiten')).toBeNull();
	expect(screen.getByText('Menge anpassen').closest('details')?.open).toBe(false);
	await fireEvent.input(screen.getByLabelText('Faktor'), { target: { value: '2' } });
	expect(screen.getByText('1.000 g')).toBeTruthy();
	expect(screen.getByText('8 Portionen (angepasst)')).toBeTruthy();
	expect(screen.getByText('Für die 20-cm-Form 350 g Mehl verwenden.')).toBeTruthy();
	expect(screen.queryByRole('navigation', { name: 'Rezeptvarianten' })).toBeNull();
	expect(screen.queryByRole('link', { name: 'Kleine Form' })).toBeNull();
	page.params = { id: '2' };
	await screen.findByRole('heading', { name: 'Kleine Form' });
	expect(screen.getByText(/Für 2 Portionen/).textContent).toBe(
		'Für 2 Portionen · 20 Min. Arbeit · 1–2 Tage Ruhezeit · 45 Min. Koch-/Backzeit · Summe der erfassten Zeiten: 1 Tag 1 Std. 5 Min. bis 2 Tage 1 Std. 5 Min.'
	);
	expect(screen.getByText('250 g')).toBeTruthy();
	expect(screen.getByText('Keine Zubereitungsschritte hinterlegt.')).toBeTruthy();
});

test('cooking mode preserves scaling, supports checklists and releases wake lock on back', async () => {
	const release = vi.fn(async () => {});
	const request = vi.fn(async () => ({ release }));
	Object.defineProperty(navigator, 'wakeLock', { configurable: true, value: { request } });
	render(RecipePage);
	await screen.findByRole('heading', { name: recipe.title });
	await fireEvent.input(screen.getByLabelText('Faktor'), { target: { value: '2' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Kochmodus' }));
	await screen.findByRole('button', { name: 'Kochmodus beenden' });
	expect(request).toHaveBeenCalledWith('screen');
	expect(screen.queryByRole('button', { name: 'Text kopieren' })).toBeNull();
	const ingredient = screen.getByRole('checkbox', { name: /1\.000 g.*Mehl/ }) as HTMLInputElement;
	await fireEvent.click(ingredient);
	expect(ingredient.checked).toBe(true);
	const step = screen.getByRole('checkbox', { name: 'Schritt 2 erledigt' }) as HTMLInputElement;
	await fireEvent.click(step);
	expect(step.checked).toBe(true);
	await fireEvent.click(screen.getByRole('button', { name: 'Kochmodus beenden' }));
	await waitFor(() => expect(release).toHaveBeenCalledOnce());
	await fireEvent.click(screen.getByRole('button', { name: 'Kochmodus' }));
	expect(
		((await screen.findByRole('checkbox', { name: /1\.000 g.*Mehl/ })) as HTMLInputElement).checked
	).toBe(false);
});
test('unsupported wake lock leaves cooking usable without a notice', async () => {
	Reflect.deleteProperty(navigator, 'wakeLock');
	render(RecipePage);
	await screen.findByRole('heading', { name: recipe.title });
	await fireEvent.click(screen.getByRole('button', { name: 'Kochmodus' }));
	await screen.findByRole('button', { name: 'Kochmodus beenden' });
	expect(screen.getAllByRole('checkbox')).toHaveLength(3);
	expect(screen.queryByText(/wach bleiben/)).toBeNull();
});
test('the recipe title is the main heading with the origin in the same header', async () => {
	render(RecipePage);
	const title = await screen.findByRole('heading', { level: 1, name: recipe.title });
	expect(title.nextElementSibling?.textContent).toBe('von Oma');
});

test('ingredients appear in separate groups and steps follow their saved order', async () => {
	vi.mocked(api.getRecipe).mockResolvedValue({
		...recipe,
		ingredient_groups: [
			...recipe.ingredient_groups,
			{ id: 2, recipe_id: 1, position: 1, name: 'Füllung' }
		],
		ingredients: [
			...recipe.ingredients,
			{ ...recipe.ingredients[0], id: 2, group_position: 1, name: 'Kirschen' }
		],
		steps: [...recipe.steps].reverse()
	});
	render(RecipePage);
	const ingredients = await screen.findByRole('region', { name: 'Zutaten' });
	const groups = within(ingredients).getAllByRole('heading', { level: 3 });
	expect(groups.map((heading) => heading.textContent)).toEqual(['Teig', 'Füllung']);
	const [dough, filling] = groups.map((heading) => within(heading.nextElementSibling as HTMLElement));
	expect(dough.getByRole('listitem').textContent).toMatch(/500 g\s*Mehl/);
	expect(filling.getByRole('listitem').textContent).toMatch(/500 g\s*Kirschen/);
	const steps = screen.getByRole('region', { name: 'Zubereitung' });
	const first = within(steps).getByText(recipe.steps[0].instruction);
	const second = within(steps).getByText(recipe.steps[1].instruction);
	expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test('guests can read the general note, share recipe text', async () => {
	render(RecipePage);
	await screen.findByRole('heading', { name: recipe.title });
	expect(screen.getByText('Abkühlen lassen.')).toBeTruthy();
	const whatsapp = screen.getByRole('link', { name: 'Per WhatsApp teilen' });
	expect(whatsapp.textContent?.trim()).toBe('Per WhatsApp teilen');
	expect(whatsapp.closest('details')).toBeNull();
	const url = new URL((whatsapp as HTMLAnchorElement).href);
	expect(url.origin).toBe('https://wa.me');
	expect(url.searchParams.get('text')).toContain(recipe.title);
	expect(url.searchParams.get('text')).toContain('Vorteig mischen.');
	await fireEvent.click(screen.getByText('Weitere Aktionen'));

});

test('the recipe shows comments separately from notes and hides them in cooking mode', async () => {
	render(RecipePage);
	const comments = await screen.findByRole('region', { name: 'Kommentare' });
	expect(comments.classList.contains('no-print')).toBe(true);
	expect(api.listRecipeComments).toHaveBeenCalledWith(recipe.id);
	expect(comments.contains(screen.getByText('Abkühlen lassen.'))).toBe(false);
	await fireEvent.click(screen.getByRole('button', { name: 'Kochmodus' }));
	expect(screen.queryByRole('region', { name: 'Kommentare' })).toBeNull();
});
const galleryImages = [
	{ id: 1, recipe_id: 1, file_path: '/media/a.jpg', alt_text: 'Kruste', is_main: true },
	{ id: 2, recipe_id: 1, file_path: '/media/b.jpg', alt_text: 'Anschnitt', is_main: false }
];

async function renderGallery(images = galleryImages) {
	vi.mocked(api.getRecipe).mockResolvedValueOnce({
		...recipe,
		images
	});
	render(RecipePage);
	return within(await screen.findByRole('group', { name: 'Rezeptbilder' }));
}

test('gallery arrows and arrow keys update the image, counter and announcement', async () => {
	const gallery = await renderGallery();
	const photo = gallery.getByRole('button', { name: 'Foto vergrößern', description: 'Kruste' });
	const previous = gallery.getByRole('button', { name: 'Vorheriges Bild' });
	const next = gallery.getByRole('button', { name: 'Nächstes Bild' });
	expect(gallery.getByText('1 / 2')).toBeTruthy();
	await fireEvent.click(previous);
	expect(gallery.getByText('2 / 2')).toBeTruthy();
	expect(gallery.getByRole('status').textContent).toBe('Bild 2 von 2');
	expect(gallery.getByRole('img', { name: 'Anschnitt' })).toBeTruthy();
	await fireEvent.click(next);
	expect(gallery.getByText('1 / 2')).toBeTruthy();
	photo.focus();
	await fireEvent.keyDown(photo, { key: 'ArrowRight' });
	expect(gallery.getByText('2 / 2')).toBeTruthy();
	expect(document.activeElement).toBe(photo);
	await fireEvent.keyDown(photo, { key: 'ArrowLeft' });
	expect(gallery.getByText('1 / 2')).toBeTruthy();
	await fireEvent.keyDown(next, { key: 'ArrowRight' });
	expect(gallery.getByText('2 / 2')).toBeTruthy();
	// A native button activated with Enter generates a click with detail 0.
	await fireEvent.click(photo, { detail: 0 });
	expect(screen.getByRole('dialog', { name: 'Fotos: Omas Brot' })).toBeTruthy();
	expect(screen.getAllByRole('img', { name: 'Anschnitt' })).toHaveLength(2);
});

test('a single gallery image has neither navigation arrows nor a position indicator', async () => {
	const gallery = await renderGallery(galleryImages.slice(0, 1));
	expect(gallery.getByRole('button', { name: 'Foto vergrößern' })).toBeTruthy();
	expect(gallery.queryByRole('button', { name: 'Vorheriges Bild' })).toBeNull();
	expect(gallery.queryByRole('button', { name: 'Nächstes Bild' })).toBeNull();
	expect(gallery.queryByText('1 / 1')).toBeNull();
	expect(gallery.queryByRole('status')).toBeNull();
});

test('swiping the recipe photo pages through the gallery without opening the viewer', async () => {
	const gallery = await renderGallery();
	const photo = gallery.getByRole<HTMLButtonElement>('button', { name: 'Foto vergrößern' });
	photo.setPointerCapture = vi.fn();
	const pointer = { pointerId: 1, isPrimary: true, pointerType: 'touch', button: 0 };
	const swipe = async (fromX: number, toX: number) => {
		await fireEvent.pointerDown(photo, { ...pointer, clientX: fromX, clientY: 100 });
		await fireEvent.pointerUp(photo, { ...pointer, clientX: toX, clientY: 104 });
		await fireEvent.click(photo, { detail: 1 });
	};
	await swipe(300, 120);
	expect(photo.setPointerCapture).toHaveBeenCalledWith(1);
	expect(gallery.getByText('2 / 2')).toBeTruthy();
	expect(page.state.photo).toBeUndefined();
	await swipe(120, 300);
	expect(gallery.getByText('1 / 2')).toBeTruthy();

	await fireEvent.pointerDown(photo, { ...pointer, clientX: 300 });
	await fireEvent.pointerDown(document.body, { ...pointer, pointerId: 2, isPrimary: false });
	await fireEvent.pointerUp(photo, { ...pointer, clientX: 120 });
	await fireEvent.click(photo, { detail: 1 });
	expect(gallery.getByText('1 / 2')).toBeTruthy();
	expect(page.state.photo).toBeUndefined();

	const rightMouse = { ...pointer, pointerType: 'mouse', button: 2 };
	await fireEvent.pointerDown(photo, { ...rightMouse, clientX: 300 });
	await fireEvent.pointerUp(photo, { ...rightMouse, clientX: 120 });
	expect(photo.setPointerCapture).toHaveBeenCalledTimes(3);
	expect(gallery.getByText('1 / 2')).toBeTruthy();

	await swipe(200, 205);
	expect(page.state.photo).toBe(true);
});
test('copy uses clear action, announces success for 3 seconds, and reports errors', async () => {
	const writeText = vi.fn(async () => {});
	Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
	render(RecipePage);
	await screen.findByRole('heading', { name: recipe.title });
	expect(screen.getByRole('button', { name: 'Link kopieren' })).toBeTruthy();
	vi.useFakeTimers();
	await fireEvent.click(screen.getByRole('button', { name: 'Text kopieren' }));
	expect(writeText.mock.calls[0][0]).toContain('Geschichte zum Rezept:\nJeden Sonntag.\nFür alle.');
	const status = screen.getByText('Rezepttext kopiert.');
	expect(status.getAttribute('role')).toBe('status');
	await vi.advanceTimersByTimeAsync(2100);
	expect(status.textContent).toBe('Rezepttext kopiert.');
	await vi.advanceTimersByTimeAsync(901);
	await waitFor(() => expect(status.textContent).toBe(''));
	writeText.mockRejectedValueOnce(new Error('denied'));
	await fireEvent.click(screen.getByRole('button', { name: 'Text kopieren' }));
	expect(screen.getByRole('alert').textContent).toContain('Kopieren ist fehlgeschlagen');
});
test('further actions closes on Escape and link copy with focus returned to its summary', async () => {
	const writeText = vi.fn(async (_text: string) => {});
	Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
	render(RecipePage);
	await screen.findByRole('heading', { name: recipe.title });
	const summary = screen.getByText('Weitere Aktionen');
	const menu = summary.closest('details')!;
	await fireEvent.click(summary);
	const copyLink = screen.getByRole('button', { name: 'Link kopieren' });
	copyLink.focus();
	await fireEvent.keyDown(copyLink, { key: 'Escape' });
	expect(menu.open).toBe(false);
	expect(document.activeElement).toBe(summary);
	await fireEvent.click(summary);
	await fireEvent.click(copyLink);
	expect(menu.open).toBe(false);
	expect(document.activeElement).toBe(summary);
	expect(writeText).toHaveBeenCalledWith(window.location.href);
	expect(screen.getByText('Link kopiert.').getAttribute('role')).toBe('status');
});
test('offline sharing offers only WhatsApp, recipe text and the original recipe link', async () => {
	const share = vi.fn();
	const writeText = vi.fn();
	const shareProperty = Object.getOwnPropertyDescriptor(navigator, 'share');
	const clipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
	Object.defineProperty(navigator, 'share', { configurable: true, value: share });
	Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
	offline.markConnection(true);
	try {
		render(RecipePage);
		await screen.findByRole('heading', { name: recipe.title });
		expect(screen.queryByRole('button', { name: 'Teilen', exact: true })).toBeNull();
		const whatsapp = screen.getByRole('link', { name: 'Per WhatsApp teilen' });
		expect(whatsapp.textContent?.trim()).toBe('Per WhatsApp teilen');
		expect(new URL((whatsapp as HTMLAnchorElement).href).searchParams.get('text')).toContain('Vorteig mischen.');
		await fireEvent.click(screen.getByRole('button', { name: 'Text kopieren' }));
		expect(writeText).toHaveBeenCalledWith(expect.stringContaining('Vorteig mischen.'));
		expect(writeText).toHaveBeenCalledWith(expect.stringContaining('Mehl'));
		await fireEvent.click(screen.getByRole('button', { name: 'Link kopieren' }));
		expect(writeText).toHaveBeenLastCalledWith(window.location.href);
		expect(share).not.toHaveBeenCalled();
	} finally {
		if (shareProperty) Object.defineProperty(navigator, 'share', shareProperty);
		else Reflect.deleteProperty(navigator, 'share');
		if (clipboard) Object.defineProperty(navigator, 'clipboard', clipboard);
		else Reflect.deleteProperty(navigator, 'clipboard');
		offline.markConnection(false);
	}
});
test('viewer uses native modal lifecycle, arrow navigation, alt text, Escape callback, focus and scroll restoration', async () => {
	const opener = document.createElement('button');
	document.body.appendChild(opener);
	opener.focus();
	document.documentElement.style.overflow = 'auto';
	const close = vi.fn();
	const { unmount } = render(PhotoViewer, {
		images: [
			{ id: 1, recipe_id: 1, file_path: '/a.jpg', alt_text: 'Kruste', is_main: true },
			{ id: 2, recipe_id: 1, file_path: '/b.jpg', alt_text: 'Anschnitt', is_main: false }
		],
		title: 'Brot',
		onclose: close
	});
	const dialog = screen.getByRole('dialog', { name: 'Fotos: Brot' });
	expect((dialog as HTMLDialogElement).open).toBe(true);
	expect(document.documentElement.style.overflow).toBe('hidden');
	const zoom = screen.getByRole('button', { name: 'Foto vergrößern' });
	const closeViewer = screen.getByRole('button', { name: 'Großansicht schließen' });
	const next = screen.getByRole('button', { name: 'Nächstes Bild' });
	expect(document.activeElement).toBe(zoom);
	await fireEvent.keyDown(zoom, { key: 'Tab', shiftKey: true });
	expect(document.activeElement).toBe(next);
	await fireEvent.keyDown(next, { key: 'Tab' });
	expect(document.activeElement).toBe(zoom);
	await fireEvent.keyDown(zoom, { key: 'Tab' });
	expect(document.activeElement).toBe(closeViewer);
	await fireEvent.click(zoom);
	zoom.focus();
	await fireEvent.keyDown(zoom, { key: 'ArrowRight', shiftKey: true });
	expect(screen.getByRole('img', { name: 'Kruste' }).style.transform).toMatch(/translate\(-40px(?:, 0px)?\)/);
	await fireEvent.keyDown(zoom, { key: 'ArrowDown', shiftKey: true });
	expect(screen.getByRole('img', { name: 'Kruste' }).style.transform).toContain('translate(-40px, -40px)');
	await fireEvent.keyDown(zoom, { key: 'Tab' });
	const resetZoom = screen.getByRole('button', { name: 'Originalgröße' });
	expect(document.activeElement).toBe(resetZoom);
	await fireEvent.click(resetZoom);
	expect(document.activeElement).toBe(zoom);
	expect(screen.getByAltText('Kruste')).toBeTruthy();
	await fireEvent.keyDown(dialog, { key: 'ArrowRight' });
	expect(screen.getByAltText('Anschnitt')).toBeTruthy();
	expect(screen.getByRole('status').textContent).toBe('Bild 2 von 2');
	await fireEvent.keyDown(dialog, { key: 'ArrowLeft' });
	expect(screen.getByRole('img', { name: 'Kruste' })).toBeTruthy();
	expect(screen.getByRole('status').textContent).toBe('Bild 1 von 2');
	await fireEvent(dialog, new Event('cancel', { cancelable: true }));
	expect(close).toHaveBeenCalledOnce();
	unmount();
	expect(document.documentElement.style.overflow).toBe('auto');
	document.documentElement.style.removeProperty('overflow');
	expect(document.activeElement).toBe(opener);
	opener.remove();
});
test('time field accepts days and preserves stored minutes when unit changes', async () => {
	render(TimeField, { id: 'rest', label: 'Ruhezeit', from: 1440, to: 2880, range: true });
	const from = screen.getByLabelText('Ruhezeit') as HTMLInputElement;
	expect(from.value).toBe('1');
	await fireEvent.change(screen.getByLabelText('Ruhezeit Einheit'), { target: { value: '60' } });
	expect(from.value).toBe('24');
	await fireEvent.input(from, { target: { value: '36' } });
	await fireEvent.change(screen.getByLabelText('Ruhezeit Einheit'), { target: { value: '1440' } });
	expect(from.value).toBe('1.5');
});

test('PDF action downloads a title-named file and reports failed exports', async () => {
	const fetchMock = vi
		.spyOn(globalThis, 'fetch')
		.mockResolvedValueOnce(
			new Response('%PDF-1.7', { headers: { 'content-type': 'application/pdf' } })
		)
		.mockImplementationOnce(async () => new Response('%PDF-1.7', { headers: { 'content-type': 'application/pdf' } }))
		.mockResolvedValueOnce(new Response('', { status: 404 }));
	Object.defineProperty(URL, 'createObjectURL', {
		configurable: true,
		value: vi.fn(() => 'blob:recipe-pdf')
	});
	Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
	let filename = '';
	vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
		filename = this.download;
	});
	render(RecipePage);
	await screen.findByRole('heading', { name: recipe.title });
	await fireEvent.click(screen.getByText('Weitere Aktionen'));
	const pdfButton = screen.getByRole('button', { name: 'Als PDF speichern' });
	await fireEvent.click(pdfButton);
	await waitFor(() => expect(filename).toBe('Omas Brot.pdf'));
	expect(fetchMock).toHaveBeenCalledWith('/api/recipes/1/pdf?factor=1', {
		credentials: 'include',
		cache: 'no-store'
	});
	await fireEvent.click(screen.getByText('Menge anpassen'));
	await fireEvent.input(screen.getByLabelText('Gewünschte Portionen'), {
		target: { value: '6' }
	});
	await fireEvent.click(pdfButton);
	expect(fetchMock).toHaveBeenLastCalledWith('/api/recipes/1/pdf?factor=1.5', {
		credentials: 'include',
		cache: 'no-store'
	});
	await waitFor(() => expect(pdfButton.disabled).toBe(false));
	await fireEvent.input(screen.getByLabelText('Gewünschte Portionen'), {
		target: { value: '5,33333' }
	});
	await fireEvent.click(pdfButton);
	expect(fetchMock).toHaveBeenLastCalledWith('/api/recipes/1/pdf?factor=1.3333', {
		credentials: 'include',
		cache: 'no-store'
	});
	expect((await screen.findByRole('alert')).textContent).toContain(
		'Das PDF konnte nicht gespeichert werden'
	);
});

test('guests can print directly without an image option or print-only image', async () => {
	const print = vi.spyOn(window, 'print').mockImplementation(() => {});
	vi.mocked(api.getRecipe).mockResolvedValueOnce({
		...recipe,
		images: [{ id: 1, recipe_id: recipe.id, file_path: '/media/brot.jpg', alt_text: 'Brot', is_main: true }]
	});
	render(RecipePage);
	await screen.findByRole('heading', { name: recipe.title });
	await fireEvent.click(screen.getByText('Weitere Aktionen'));
	const button = screen.getByRole('button', { name: 'Drucken' });
	expect(screen.queryByText('Mit Bildern')).toBeNull();
	expect(screen.queryByText('Ohne Bilder')).toBeNull();
	const images = Array.from(document.querySelectorAll('article.recipe-detail img'));
	expect(images.length).toBeGreaterThan(0);
	expect(images.every((image) => image.closest('.no-print'))).toBe(true);
	await fireEvent.click(screen.getByText('Menge anpassen'));
	await fireEvent.input(screen.getByLabelText('Gewünschte Portionen'), {
		target: { value: '6' }
	});
	expect(screen.getByText(/750 g/).closest('.no-print')).toBeNull();
	await fireEvent.click(button);
	expect(print).toHaveBeenCalledOnce();
});

test('late favorite mutation cannot mark or remove the next recipe favorite', async () => {
	auth.user = { id: 1, username: 'reader', role: 'reader' } as typeof auth.user;
	let resolveAdd!: (value: Awaited<ReturnType<typeof api.addFavorite>>) => void;
	vi.mocked(api.addFavorite).mockImplementationOnce(
		() =>
			new Promise((resolve) => {
				resolveAdd = resolve;
			})
	);
	render(RecipePage);
	await screen.findByRole('heading', { name: recipe.title });
	await waitFor(() =>
		expect((screen.getByRole('button', { name: 'Merken' }) as HTMLButtonElement).disabled).toBe(
			false
		)
	);
	await fireEvent.click(screen.getByRole('button', { name: 'Merken' }));
	expect(api.listFavorites).toHaveBeenCalledWith(undefined, 1);
	expect(api.addFavorite).toHaveBeenCalledWith(1, 1);
	page.params = { id: '2' };
	await screen.findByRole('heading', { name: 'Kleine Form' });
	await waitFor(() =>
		expect((screen.getByRole('button', { name: 'Merken' }) as HTMLButtonElement).disabled).toBe(
			false
		)
	);
	resolveAdd({ id: 99, recipe_id: 1 } as Awaited<ReturnType<typeof api.addFavorite>>);
	await new Promise((resolve) => setTimeout(resolve, 0));
	expect(screen.getByRole('button', { name: 'Merken' }).getAttribute('aria-pressed')).toBe('false');
	await fireEvent.click(screen.getByRole('button', { name: 'Merken' }));
	expect(api.addFavorite).toHaveBeenLastCalledWith(2, 1);
	expect(api.removeFavorite).not.toHaveBeenCalled();
});

test('cooking retains complete cooking content and scaled quantities', async () => {
	render(RecipePage);
	await screen.findByRole('heading', { name: recipe.title });
	await fireEvent.click(screen.getByRole('button', { name: 'Kochmodus' }));
	expect(document.querySelector('.story')?.textContent).toContain('Jeden Sonntag.');
	expect(document.querySelector('.facts')?.textContent).toContain('Über 2 Tage');
	expect(document.querySelector('.summary')?.textContent).toContain('Mit Vorteig');
	expect(document.querySelector('.extra')?.textContent).toContain('Abkühlen lassen.');
	expect(document.querySelector('.ingredient-list')?.textContent).toContain('500 g');
});

test('step times replace the manual time, add up in the total and announce the replacement after saving', async () => {
	const timed = {
		...recipe,
		preparation_days: 4,
		preparation_time: null,
		rest_time: 1440,
		rest_time_max: 2880,
		cooking_time: 45,
		steps: [
			{ ...recipe.steps[0], duration_minutes: 20, time_kind: 'cooking' as const },
			{ ...recipe.steps[1], duration_minutes: 1500, time_kind: 'rest' as const }
		]
	};
	vi.mocked(api.getRecipe).mockResolvedValue(timed);
	page.url = new URL('http://localhost/recipes/1?timenotice=1');
	render(RecipePage);
	await screen.findByRole('heading', { name: 'Omas Brot' });
	expect(screen.getByText(/Über 4 Tage/).textContent).toBe(
		'Über 4 Tage · 1 Tag 1 Std. Ruhezeit · 20 Min. Koch-/Backzeit · Summe der erfassten Zeiten: 1 Tag 1 Std. 20 Min. · Für 4 Portionen'
	);
	expect(
		screen.getByText(
			'Koch-/Backzeit: Aus den Schritten werden 20 Min. angezeigt statt der manuell eingetragenen 45 Min. Die 45 Min. bleiben gespeichert.'
		)
	).toBeTruthy();
	expect(screen.getByText('Koch-/Backzeit: 20 Min.')).toBeTruthy();
	expect(screen.getByText(/manuell eingetragenen 1–2 Tage\. Die 1–2 Tage bleiben gespeichert\./)).toBeTruthy();
	page.url = new URL('http://localhost/');
});

test('step time inputs set duration and kind together and clear both', async () => {
	const form = {
		title: 'Brot',
		preparation_days: 1,
		ingredients: [],
		ingredient_groups: [],
		steps: [
			{
				position: 0,
				instruction: 'Backen',
				heading: null,
				is_important: false,
				note: null,
				duration_minutes: null,
				time_kind: null
			}
		]
	} as never as import('../../src/lib/types').RecipeInput;
	render(RecipeFieldsForm, { form, categories: [] });
	await fireEvent.click(screen.getByRole('button', { name: /Zeit, Notiz/ }));
	const kind = screen.getByLabelText('Zeitart von Schritt 1') as HTMLSelectElement;
	expect(kind.disabled).toBe(true);
	const minutes = screen.getByLabelText('Dauer von Schritt 1 in Minuten');
	await fireEvent.input(minutes, { target: { value: '25' } });
	expect([form.steps[0].duration_minutes, form.steps[0].time_kind]).toEqual([25, 'preparation']);
	await fireEvent.change(kind, { target: { value: 'rest' } });
	expect(form.steps[0].time_kind).toBe('rest');
	await fireEvent.input(minutes, { target: { value: '' } });
	expect([form.steps[0].duration_minutes, form.steps[0].time_kind]).toEqual([null, null]);
});

const dayStep = (position: number, day: number) => ({
	position,
	instruction: `Schritt ${position + 1}`,
	heading: null,
	is_important: false,
	note: null,
	duration_minutes: null,
	time_kind: null,
	day
});
const dayForm = () =>
	({
		title: 'Brot',
		preparation_days: 3,
		day_titles: ['Einlegen', '', 'Backen'],
		preparation_time: null,
		cooking_time: null,
		cooking_time_max: null,
		rest_time: null,
		rest_time_max: null,
		ingredients: [],
		ingredient_groups: [],
		steps: [dayStep(0, 1), dayStep(1, 3), dayStep(2, 2)]
	}) as never as import('../../src/lib/types').RecipeInput;

test('reducing the preparation days makes the user reassign steps from removed days first', async () => {
	const form = dayForm();
	render(RecipeFieldsForm, { form, categories: [] });
	await fireEvent.click(screen.getByRole('button', { name: /Mehr Details/ }));
	const days = screen.getByLabelText(/Verteilt über/);
	await fireEvent.change(days, { target: { value: '2' } });
	expect(form.preparation_days).toBe(3);
	const dialog = await screen.findByRole('dialog');
	expect(dialog.textContent).toContain('Schritt 2');
	expect(dialog.textContent).not.toContain('Schritt 3');
	const apply = screen.getByRole('button', { name: 'Zuordnung übernehmen' }) as HTMLButtonElement;
	expect(apply.disabled).toBe(true);
	await fireEvent.change(screen.getByLabelText('Neuer Tag für Schritt 2'), {
		target: { value: '2' }
	});
	expect(apply.disabled).toBe(false);
	await fireEvent.click(apply);
	expect(form.preparation_days).toBe(2);
	expect(form.steps.map((step) => step.day)).toEqual([1, 2, 2]);
	expect(form.day_titles).toEqual(['Einlegen', '']);
});

test('cancelling the reassignment keeps days, steps and titles unchanged', async () => {
	const form = dayForm();
	render(RecipeFieldsForm, { form, categories: [] });
	await fireEvent.click(screen.getByRole('button', { name: /Mehr Details/ }));
	const days = screen.getByLabelText(/Verteilt über/) as HTMLInputElement;
	await fireEvent.change(days, { target: { value: '1' } });
	await fireEvent.click(await screen.findByRole('button', { name: 'Abbrechen' }));
	expect(form.preparation_days).toBe(3);
	expect(form.steps.map((step) => step.day)).toEqual([1, 3, 2]);
	expect(form.day_titles).toEqual(['Einlegen', '', 'Backen']);
	expect(days.value).toBe('3');
});

test('reducing days without steps in the removed days needs no reassignment', async () => {
	const form = dayForm();
	form.steps = [dayStep(0, 1)];
	render(RecipeFieldsForm, { form, categories: [] });
	await fireEvent.click(screen.getByRole('button', { name: /Mehr Details/ }));
	await fireEvent.change(screen.getByLabelText(/Verteilt über/), { target: { value: '2' } });
	expect(screen.queryByRole('dialog')).toBeNull();
	expect(form.preparation_days).toBe(2);
	expect(form.day_titles).toEqual(['Einlegen', '']);
});

test('detail view groups steps into day sections and single-day recipes show none', async () => {
	const multi = {
		...recipe,
		preparation_days: 2,
		day_titles: ['Einlegen'],
		steps: [
			{ ...recipe.steps[1], heading: null, day: 2, instruction: 'Backen.' },
			{ ...recipe.steps[0], heading: null, day: 1, instruction: 'Ansetzen.' }
		]
	};
	vi.mocked(api.getRecipe).mockResolvedValue(multi);
	render(RecipePage);
	await screen.findByRole('heading', { name: 'Omas Brot' });
	const headings = [...document.querySelectorAll('.step-heading')].map((h) =>
		h.textContent?.trim()
	);
	expect(headings).toEqual(['Tag 1 – Einlegen', 'Tag 2']);
	expect(screen.getByText('Ansetzen.').compareDocumentPosition(screen.getByText('Backen.'))).toBe(
		Node.DOCUMENT_POSITION_FOLLOWING
	);
});

test('recipe cards show the effective total from step times with manual fallback', () => {
	const card = {
		...recipe,
		preparation_days: 1,
		preparation_time: 10,
		cooking_time: 45,
		rest_time: null,
		rest_time_max: null,
		step_times: { cooking: 35 }
	};
	render(RecipeCard, { recipe: card, layout: 'recent' });
	expect(screen.getByText(/45 Min\./)).toBeTruthy();
});

test('recipes without saved servings use one portion as the scaling baseline without writing back', async () => {
	vi.mocked(api.getRecipe).mockResolvedValueOnce({
		...structuredClone(recipe), servings: null, preparation_days: 1
	});
	render(RecipePage);
	await screen.findByRole('heading', { name: 'Omas Brot' });
	const portions = screen.getByLabelText('Gewünschte Portionen') as HTMLInputElement;
	expect(portions.value).toBe('1');
	await fireEvent.input(portions, { target: { value: '2' } });
	expect(screen.getByText('1.000 g')).toBeTruthy();
	expect(screen.getByText('2 Portionen (angepasst)')).toBeTruthy();
	await fireEvent.input(portions, { target: { value: '0' } });
	expect(screen.getByText('Bitte eine Zahl größer als 0 eingeben.')).toBeTruthy();
	expect(screen.getByText('1.000 g')).toBeTruthy();
	await fireEvent.click(screen.getByRole('button', { name: 'Zurücksetzen' }));
	expect(screen.getByText('500 g')).toBeTruthy();
	expect(screen.queryByText('1.000 g')).toBeNull();
});

test('replaces an open detail when the snapshot no longer contains its recipe', async () => {
	render(RecipePage);
	await screen.findByRole('heading', { name: recipe.title });
	vi.mocked(api.getRecipe).mockRejectedValue(new api.ApiError(404, 'Not found'));
	try {
		offline.generation = 'new-recipe-generation';
		await screen.findByText('Dieses Rezept wurde nicht gefunden.');
		expect(screen.queryByRole('heading', { name: recipe.title })).toBeNull();
	} finally {
		offline.generation = null;
	}
});

test('switches to cached read-only ratings when the recipe goes offline', async () => {
	auth.user = { id: 1, username: 'Lena', is_active: true, role: 'reader' } as never;
	offline.markConnection(false);
	vi.mocked(api.getRecipeRatings)
		.mockResolvedValueOnce({ average: 5, count: 1, ratings: [{ username: 'Lena', stars: 5 }] })
		.mockResolvedValueOnce({
			average: 4.5,
			count: 1,
			ratings: [{ username: 'Lena', stars: 4.5 }]
		});
	try {
		render(RecipePage);
		await screen.findByRole('button', { name: /5,0 von 5.*1 Bewertung/ });
		offline.markConnection(true);
		await screen.findByRole('img', { name: /4,5 von 5.*1 Bewertung/ });
		expect(screen.queryByRole('button', { name: /Rezept bewerten/ })).toBeNull();
	} finally {
		offline.markConnection(false);
	}
});

test('renders a recipe opened from a direct offline link', async () => {
	page.params = { id: '5' };
	page.url = new URL('http://localhost/recipes/5');
	vi.mocked(api.getRecipe).mockResolvedValue({ ...recipe, id: 5 });
	offline.markConnection(true);
	try {
		render(RecipePage);
		await screen.findByRole('heading', { name: recipe.title });
		expect(api.getRecipe).toHaveBeenCalledWith(5);
		expect(screen.getByRole('button', { name: 'Kochmodus' })).toBeTruthy();
	} finally {
		offline.markConnection(false);
	}
});
