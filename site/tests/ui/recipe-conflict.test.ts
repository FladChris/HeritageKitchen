import { expect, test, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import RecipeConflictDialog from '../../src/lib/components/RecipeConflictDialog.svelte';
import type { RecipeConflict, RecipeInput } from '../../src/lib/types';

const draft: RecipeInput = {
	title: 'Mein Apfelkuchen',
	summary: null,
	history: null,
	preparation_days: 1,
	day_titles: null,
	preparation_time: null,
	cooking_time: null,
	cooking_time_max: null,
	rest_time: null,
	rest_time_max: null,
	servings: null,
	origin_person: null,
	notes: 'Mein Entwurf bleibt erhalten',
	important_notes: null,
	category_id: 1,
	ingredients: [],
	ingredient_groups: [],
	steps: []
};

const conflict: RecipeConflict = {
	code: 'recipe_version_conflict',
	expected_version: 3,
	current_version: 4,
	changes: {
		notes: { before: 'Vorher', after: 'Neuer Stand' }
	},
	current: { title: 'Apfelkuchen', notes: 'Neuer Stand' }
};

test('concurrent edits show server changes and the retained local draft', async () => {
	const oncontinue = vi.fn();
	const onleave = vi.fn();
	const onoverwrite = vi.fn();
	render(RecipeConflictDialog, {
		conflict,
		draft,
		busy: false,
		oncontinue,
		onleave,
		onoverwrite
	});

	expect(screen.getByRole('dialog', { name: 'Rezept wurde zwischenzeitlich geändert' })).toBeTruthy();
	expect(screen.getByText(/Version 3 ist nicht mehr/)).toBeTruthy();
	expect(screen.getByText('Vorher')).toBeTruthy();
	expect(screen.getByText('Neuer Stand')).toBeTruthy();
	expect(screen.getByText('Mein Entwurf bleibt erhalten')).toBeTruthy();
	await fireEvent.click(screen.getByRole('button', { name: 'Weiter bearbeiten' }));
	expect(oncontinue).toHaveBeenCalledTimes(1);
	await fireEvent.click(screen.getByRole('button', { name: 'Bearbeitung verlassen' }));
	expect(onleave).toHaveBeenCalledTimes(1);
	await fireEvent.click(screen.getByRole('button', { name: 'Trotzdem überschreiben' }));
	expect(onoverwrite).toHaveBeenCalledTimes(1);
});

test('draft shows the category name and readable ingredients and steps', () => {
	render(RecipeConflictDialog, {
		conflict: {
			...conflict,
			changes: {
				category_name: { before: 'Kuchen', after: 'Desserts' },
				ingredients: { before: [], after: [{ position: 0, name: 'Mehl', amount: '500', unit: 'g', note: null }] },
				steps: { before: [], after: [{ position: 0, instruction: 'Backen', heading: null }] }
			}
		},
		draft: { ...draft, category_id: 2 },
		categories: [
			{ id: 1, name: 'Kuchen', recipe_count: 0, description: null, image_path: null, image_alt_text: null },
			{ id: 2, name: 'Desserts', recipe_count: 0, description: null, image_path: null, image_alt_text: null }
		],
		busy: false,
		oncontinue: () => {},
		onleave: () => {},
		onoverwrite: () => {}
	});
	expect(screen.getAllByText('Desserts').length).toBeGreaterThan(1);
	expect(screen.getByText('1. 500 g Mehl')).toBeTruthy();
	expect(screen.getByText('1. Backen')).toBeTruthy();
	expect(document.body.textContent).not.toContain('"position"');
});

test('conflict field headings retain shared labels, context-specific names and unknown fields', () => {
	render(RecipeConflictDialog, {
		conflict: {
			...conflict,
			changes: {
				important_notes: { before: null, after: 'Vorsichtig backen' },
				day_titles: { before: null, after: ['Vorbereitung'] },
				steps: { before: [], after: [] },
				images: { before: [], after: [] },
				future_field: { before: null, after: 'Neuer Wert' }
			}
		},
		draft,
		busy: false,
		oncontinue: vi.fn(),
		onleave: vi.fn(),
		onoverwrite: vi.fn()
	});
	for (const name of ['Wichtige Hinweise', 'Tagesnamen', 'Zubereitungsschritte', 'Rezeptbilder', 'future_field']) {
		expect(screen.getByRole('heading', { name, exact: true })).toBeTruthy();
	}
});

test('the conflict uses the native modal boundary, focuses its heading and restores the opener on cancel', async () => {
	const opener = document.createElement('button');
	document.body.append(opener);
	opener.focus();
	const showModal = vi.spyOn(HTMLDialogElement.prototype, 'showModal');
	try {
		const { unmount } = render(RecipeConflictDialog, {
			conflict,
			draft,
			busy: false,
			oncontinue: () => unmount(),
			onleave: vi.fn(),
			onoverwrite: vi.fn()
		});
		const dialog = screen.getByRole<HTMLDialogElement>('dialog', { name: /zwischenzeitlich geändert/ });
		expect(showModal.mock.contexts).toContain(dialog);
		expect(document.activeElement).toBe(screen.getByRole('heading', { name: /zwischenzeitlich geändert/ }));
		const differences = screen.getByRole('region', { name: 'Geänderte Rezeptfelder' });
		expect(differences.tabIndex).toBe(0);
		for (const name of ['Weiter bearbeiten', 'Bearbeitung verlassen', 'Trotzdem überschreiben']) {
			const action = screen.getByRole<HTMLButtonElement>('button', { name });
			expect(action.tabIndex).toBe(0);
			action.focus();
			expect(document.activeElement).toBe(action);
		}
		// jsdom only models the cancel event that Escape generates in the browser.
		await fireEvent(dialog, new Event('cancel', { cancelable: true }));
		expect(dialog.open).toBe(false);
		expect(document.activeElement).toBe(opener);
	} finally {
		opener.remove();
	}
});
