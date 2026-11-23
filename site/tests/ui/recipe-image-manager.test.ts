import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';
import * as api from '$lib/api';
import RecipeImageManager from '$lib/components/RecipeImageManager.svelte';
import type { RecipeImage } from '$lib/types';

vi.mock('$lib/api', async (importOriginal) => ({
	...await importOriginal<typeof import('$lib/api')>(),
	uploadRecipeImage: vi.fn(),
	cropRecipeImage: vi.fn(),
	setMainImage: vi.fn(),
	deleteRecipeImage: vi.fn(),
	reorderRecipeImages: vi.fn(),
	updateRecipeImageAltText: vi.fn()
}));

vi.mock('cropperjs', () => ({
	default: class {
		destroy() {}
		getCroppedCanvas() {
			return { toBlob: (done: BlobCallback) => done(new Blob(['photo'], { type: 'image/jpeg' })) };
		}
	}
}));

const image = (id: number, extra: Partial<RecipeImage> = {}): RecipeImage => ({
	id,
	recipe_id: 1,
	file_path: `/media/${id}.jpg`,
	alt_text: null,
	is_main: false,
	...extra
});

function gallery(ids: number[], mainId = ids[0]) {
	return ids.map((id) => image(id, { is_main: id === mainId }));
}

function order() {
	return [...document.querySelectorAll('.image-item img')].map((img) => img.getAttribute('src'));
}

function openOrder(position: number) {
	return fireEvent.click(screen.getByRole('button', { name: `Bild ${position} sortieren` }));
}

beforeEach(() => vi.resetAllMocks());

test.each([
	['Datei auswählen', '  Apfelkuchen  ', 'Apfelkuchen'],
	['Foto aufnehmen', 'Apfelkuchen von oben', 'Apfelkuchen von oben'],
	['Foto aufnehmen', '  ', undefined]
])('%s lets the editor submit optional alt text with the photo', async (name, input, altText) => {
	vi.stubGlobal('URL', class extends URL {
		static createObjectURL() { return 'blob:photo'; }
		static revokeObjectURL() {}
	});
	try {
		vi.mocked(api.uploadRecipeImage).mockResolvedValue(image(1, { alt_text: altText ?? null }));
		render(RecipeImageManager, { recipeId: 1, version: 7, images: [] });
		expect(screen.getByText('Bilder hinzufügen')).toBeTruthy();
		expect(screen.getByText('0 von 20 Bildern')).toBeTruthy();
		const picker = screen.getByLabelText(name);
		if (name === 'Foto aufnehmen') expect(picker.getAttribute('capture')).toBe('environment');
		await fireEvent.change(picker, {
			target: { files: [new File(['photo'], 'photo.jpg', { type: 'image/jpeg' })] }
		});
		const dialog = await screen.findByRole('dialog');
		await fireEvent.input(within(dialog).getByRole('textbox', { name: 'Alt-Text (optional)' }), {
			target: { value: input }
		});
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Zuschneiden und speichern' }));
		expect(api.uploadRecipeImage).toHaveBeenCalledWith(1, expect.any(File), 7, altText);
		await waitFor(() => expect(order()).toEqual(['/media/1.jpg']));
		expect(screen.getByText('1 von 20 Bildern')).toBeTruthy();
	} finally {
		vi.unstubAllGlobals();
	}
});

test('an existing image is loaded and cropped using the held recipe version', async () => {
	vi.stubGlobal('URL', class extends URL {
		static createObjectURL() { return 'blob:photo'; }
		static revokeObjectURL() {}
	});
	try {
		const fetchImage = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('photo', {
			headers: { 'Content-Type': 'image/jpeg' }
		}));
		vi.mocked(api.cropRecipeImage).mockResolvedValue(image(1, { file_path: '/cropped.jpg' }));
		render(RecipeImageManager, { recipeId: 1, version: 7, images: gallery([1]) });
		await fireEvent.click(screen.getByRole('button', { name: 'Bild 1 zuschneiden' }));
		const dialog = await screen.findByRole('dialog', { name: 'Bild zuschneiden' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Zuschneiden und speichern' }));
		expect(fetchImage).toHaveBeenCalledExactlyOnceWith('/media/1.jpg');
		expect(api.cropRecipeImage).toHaveBeenCalledExactlyOnceWith(1, expect.any(File), 7);
		await waitFor(() => expect(order()).toEqual(['/cropped.jpg']));
	} finally {
		vi.unstubAllGlobals();
	}
});

test('a failed existing-image load reports an error without opening the cropper', async () => {
	vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 404 }));
	render(RecipeImageManager, { recipeId: 1, version: 7, images: gallery([1]) });
	await fireEvent.click(screen.getByRole('button', { name: 'Bild 1 zuschneiden' }));
	expect((await screen.findByRole('alert')).textContent).toBe('Bild konnte nicht geladen werden.');
	expect(screen.queryByRole('dialog')).toBeNull();
	expect(order()).toEqual(['/media/1.jpg']);
	expect(api.cropRecipeImage).not.toHaveBeenCalled();
});

test('moving an image stores the new gallery order and shows it', async () => {
	vi.mocked(api.reorderRecipeImages).mockResolvedValue(gallery([2, 1, 3], 1));
	render(RecipeImageManager, { recipeId: 1, version: 7, images: gallery([1, 2, 3]) });
	await openOrder(2);
	await fireEvent.click(screen.getByRole('button', { name: 'Bild 2 nach vorn' }));
	expect(api.reorderRecipeImages).toHaveBeenCalledWith(1, [2, 1, 3], 7);
	await waitFor(() => expect(order()).toEqual(['/media/2.jpg', '/media/1.jpg', '/media/3.jpg']));
});

test('arrow keys on the drag handle reorder the image and keep its focus', async () => {
	vi.mocked(api.reorderRecipeImages).mockResolvedValue(gallery([2, 1, 3], 1));
	render(RecipeImageManager, { recipeId: 1, version: 7, images: gallery([1, 2, 3]) });
	const handle = screen.getByRole('button', { name: 'Bild 2 sortieren' });
	handle.focus();
	await fireEvent.keyDown(handle, { key: 'ArrowUp' });
	expect(api.reorderRecipeImages).toHaveBeenCalledExactlyOnceWith(1, [2, 1, 3], 7);
	expect(await screen.findByText('Bild von Position 2 auf Position 1 verschoben.')).toBeTruthy();
	expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Bild 1 sortieren' }));
});

test('dropping a handle on a distant image inserts it at the target position', async () => {
	vi.mocked(api.reorderRecipeImages).mockResolvedValue(gallery([2, 3, 1], 1));
	render(RecipeImageManager, { recipeId: 1, version: 7, images: gallery([1, 2, 3]) });
	const dataTransfer = { setData: vi.fn(), effectAllowed: '', dropEffect: '' };
	const handle = screen.getByRole('button', { name: 'Bild 1 sortieren' });
	const target = screen.getByRole('group', { name: 'Bild 3' });
	await fireEvent.dragStart(handle, { dataTransfer });
	await fireEvent.dragOver(target, { dataTransfer });
	await fireEvent.drop(target, { dataTransfer });
	expect(dataTransfer.dropEffect).toBe('move');
	expect(api.reorderRecipeImages).toHaveBeenCalledExactlyOnceWith(1, [2, 3, 1], 7);
	expect(order()).toEqual(['/media/2.jpg', '/media/3.jpg', '/media/1.jpg']);
});

test('files dropped on the upload tile go through cropping one at a time', async () => {
	vi.stubGlobal('URL', class extends URL {
		static createObjectURL() { return 'blob:photo'; }
		static revokeObjectURL() {}
	});
	try {
		vi.mocked(api.uploadRecipeImage).mockResolvedValueOnce(image(1)).mockResolvedValueOnce(image(2));
		const view = render(RecipeImageManager, { recipeId: 1, version: 7, images: [] });
		const tile = screen.getByText('Bilder hinzufügen').closest('li')!;
		const files = ['first.jpg', 'second.jpg'].map((name) => new File(['photo'], name, { type: 'image/jpeg' }));
		const dataTransfer = { files, types: ['Files'], dropEffect: '' };
		await fireEvent.dragEnter(tile, { dataTransfer });
		expect(dataTransfer.dropEffect).toBe('copy');
		await fireEvent.drop(tile, { dataTransfer });
		await fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Zuschneiden und speichern' }));
		expect(api.uploadRecipeImage).toHaveBeenCalledTimes(1);
		await view.rerender({ version: 8, images: gallery([1]) });
		await fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Zuschneiden und speichern' }));
		expect(api.uploadRecipeImage).toHaveBeenNthCalledWith(2, 1, expect.any(File), 8, undefined);
		expect(screen.getByText('2 von 20 Bildern')).toBeTruthy();
	} finally {
		vi.unstubAllGlobals();
	}
});

test('dropping an unsupported file explains the allowed formats', async () => {
	render(RecipeImageManager, { recipeId: 1, version: 7, images: [] });
	const tile = screen.getByText('Bilder hinzufügen').closest('li')!;
	const files = [new File(['text'], 'notes.txt', { type: 'text/plain' })];
	await fireEvent.drop(tile, { dataTransfer: { files } });
	expect(screen.getByRole('alert').textContent).toContain('JPEG, PNG oder WebP');
	expect(screen.queryByRole('dialog')).toBeNull();
	expect(api.uploadRecipeImage).not.toHaveBeenCalled();
});

test('a failed reorder keeps the displayed order and reports the error', async () => {
	vi.mocked(api.reorderRecipeImages).mockRejectedValue(new Error('offline'));
	render(RecipeImageManager, { recipeId: 1, version: 7, images: gallery([1, 2]) });
	await openOrder(1);
	await fireEvent.click(screen.getByRole('button', { name: 'Bild 1 nach hinten' }));
	expect((await screen.findByRole('alert')).textContent).toContain('Reihenfolge');
	expect(order()).toEqual(['/media/1.jpg', '/media/2.jpg']);
});

test('first image cannot move forward and last image cannot move back', async () => {
	render(RecipeImageManager, { recipeId: 1, version: 7, images: gallery([1, 2]) });
	await openOrder(1);
	expect(screen.getByRole('button', { name: 'Bild 1 nach vorn' }).getAttribute('aria-disabled')).toBe('true');
	await openOrder(2);
	expect(screen.getByRole('button', { name: 'Bild 2 nach hinten' }).getAttribute('aria-disabled')).toBe('true');
});

test('the alt text of an existing image can be changed and cleared', async () => {
	vi.mocked(api.updateRecipeImageAltText).mockImplementation(async (id, altText) =>
		image(id, { alt_text: altText })
	);
	render(RecipeImageManager, {
		recipeId: 1, version: 7,
		images: [image(1, { alt_text: 'Kuchen', is_main: true })]
	});
	expect(screen.queryByRole('textbox', { name: 'Alt-Text für Bild 1' })).toBeNull();
	await fireEvent.click(screen.getByRole('button', { name: 'Alt-Text für Bild 1 bearbeiten' }));
	const field = screen.getByRole('textbox', { name: 'Alt-Text für Bild 1' }) as HTMLInputElement;
	expect(field.value).toBe('Kuchen');
	await fireEvent.input(field, { target: { value: 'Apfelkuchen auf Teller' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Alt-Text für Bild 1 speichern' }));
	expect(api.updateRecipeImageAltText).toHaveBeenLastCalledWith(1, 'Apfelkuchen auf Teller', 7);
	await fireEvent.input(field, { target: { value: '' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Alt-Text für Bild 1 speichern' }));
	expect(api.updateRecipeImageAltText).toHaveBeenLastCalledWith(1, null, 7);
});

test('removing the main image makes the first remaining image the main image', async () => {
	vi.mocked(api.deleteRecipeImage).mockResolvedValue(undefined);
	render(RecipeImageManager, { recipeId: 1, version: 7, images: gallery([1, 3, 2], 1) });
	await fireEvent.click(screen.getByRole('button', { name: 'Bild 1 entfernen' }));
	const dialog = await screen.findByRole('dialog', { name: 'Bild entfernen?' });
	expect(api.deleteRecipeImage).not.toHaveBeenCalled();
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Abbrechen' }));
	expect(screen.queryByRole('dialog')).toBeNull();
	expect(api.deleteRecipeImage).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByRole('button', { name: 'Bild 1 entfernen' }));
	await fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Entfernen' }));
	await waitFor(() => expect(order()).toEqual(['/media/3.jpg', '/media/2.jpg']));
	expect(screen.getAllByText('Hauptbild')).toHaveLength(1);
	expect(api.deleteRecipeImage).toHaveBeenCalledExactlyOnceWith(1, 7);
	const first = document.querySelector('.image-item') as HTMLElement;
	expect(within(first).getByText('Hauptbild')).toBeTruthy();
});

test('the star selects the main image and moves the badge', async () => {
	vi.mocked(api.setMainImage).mockResolvedValue(image(2, { is_main: true }));
	render(RecipeImageManager, { recipeId: 1, version: 7, images: gallery([1, 2]) });
	const star = screen.getByRole('button', { name: 'Bild 2 als Hauptbild festlegen' });
	expect(star.getAttribute('aria-pressed')).toBe('false');
	await fireEvent.click(star);
	expect(api.setMainImage).toHaveBeenCalledExactlyOnceWith(2, 7);
	expect(star.getAttribute('aria-pressed')).toBe('true');
	expect(within(screen.getByRole('group', { name: 'Bild 2' })).getByText('Hauptbild')).toBeTruthy();
	expect(screen.getAllByText('Hauptbild')).toHaveLength(1);
});

test('twenty images block further uploads with a clear hint', () => {
	render(RecipeImageManager, {
		recipeId: 1, version: 7,
		images: gallery(Array.from({ length: 20 }, (_, index) => index + 1))
	});
	expect(screen.getByText('20 von 20 Bildern')).toBeTruthy();
	expect(screen.getByText(/Maximal 20 Bilder/)).toBeTruthy();
	for (const input of document.querySelectorAll<HTMLInputElement>('input[type="file"]')) {
		expect(input.disabled).toBe(true);
	}
});

test('image changes use the current parent version and surface conflicts without changing images', async () => {
	vi.mocked(api.reorderRecipeImages).mockResolvedValue(gallery([2, 1]));
	const view = render(RecipeImageManager, { recipeId: 1, version: 7, images: gallery([1, 2]) });
	await openOrder(2);
	await fireEvent.click(screen.getByRole('button', { name: 'Bild 2 nach vorn' }));
	await waitFor(() => expect(order()).toEqual(['/media/2.jpg', '/media/1.jpg']));
	await view.rerender({ recipeId: 1, version: 8, images: gallery([2, 1]) });
	vi.mocked(api.reorderRecipeImages).mockRejectedValue(new api.ApiError(409, 'Conflict', {
		code: 'recipe_version_conflict', current_version: 9
	}));
	await openOrder(2);
	await fireEvent.click(screen.getByRole('button', { name: 'Bild 2 nach vorn' }));
	expect(api.reorderRecipeImages).toHaveBeenLastCalledWith(1, [1, 2], 8);
	expect((await screen.findByRole('alert')).textContent).toContain('Rezept wurde inzwischen geändert');
	expect(order()).toEqual(['/media/2.jpg', '/media/1.jpg']);
});
