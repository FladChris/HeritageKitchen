import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';
import * as api from '$lib/api';
import RecipeRatings from '$lib/components/RecipeRatings.svelte';
import { auth } from '$lib/stores/auth.svelte';
import type { RecipeRatingSummary, User } from '$lib/types';

vi.mock('$lib/api', () => ({
	getRecipeRatings: vi.fn(),
	saveRecipeRating: vi.fn(),
	removeRecipeRating: vi.fn()
}));

const empty: RecipeRatingSummary = { average: null, count: 0, ratings: [] };
const rated: RecipeRatingSummary = {
	average: 5,
	count: 2,
	ratings: [
		{ username: 'Lena', stars: 4.5 },
		{ username: 'Oma Hilde', stars: 5 }
	]
};

beforeEach(() => {
	vi.resetAllMocks();
	auth.user = null;
	vi.mocked(api.getRecipeRatings).mockResolvedValue(rated);
});

test.each([null, false, true])('only active users online can open a rating dialog (%s)', async (active) => {
	auth.user = active === null ? null : { username: 'Lena', is_active: active } as User;
	render(RecipeRatings, { recipeId: 1, readOnly: active === true });
	const average = await screen.findByRole('img', { name: '5,0 von 5 (2 Bewertungen)' });
	await fireEvent.click(average);
	expect(screen.queryByRole('dialog')).toBeNull();
});

test('a reader can save, replace, and remove their half-star rating', async () => {
	auth.user = { id: 1, username: 'Lena', role: 'reader', is_active: true } as User;
	vi.mocked(api.getRecipeRatings).mockResolvedValue(empty);
	vi.mocked(api.saveRecipeRating)
		.mockResolvedValueOnce({ average: 4.5, count: 1, ratings: [rated.ratings[0]] })
		.mockResolvedValueOnce({ average: 4, count: 1, ratings: [{ username: 'Lena', stars: 4 }] });
	vi.mocked(api.removeRecipeRating).mockResolvedValue(empty);
	render(RecipeRatings, { recipeId: 1 });
	const trigger = await screen.findByRole('button', { name: /Noch nicht bewertet/ });
	trigger.focus();
	await fireEvent.click(trigger);
	const dialog = within(screen.getByRole('dialog', { name: 'Rezept bewerten' }));
	const save = dialog.getByRole<HTMLButtonElement>('button', { name: 'Bewerten' });
	expect(save.disabled).toBe(true);
	expect(dialog.getAllByRole('radio')).toHaveLength(9);
	const halfStar = dialog.getByRole<HTMLInputElement>('radio', { name: '4,5 Sterne' });
	halfStar.focus();
	expect(document.activeElement).toBe(halfStar);
	await fireEvent.click(halfStar);
	await fireEvent.click(save);
	expect(api.saveRecipeRating).toHaveBeenLastCalledWith(1, 4.5);
	await screen.findByRole('button', { name: /4,5 von 5.*1 Bewertung/ });
	expect(document.activeElement).toBe(trigger);

	await fireEvent.click(trigger);
	expect(screen.getByRole<HTMLInputElement>('radio', { name: '4,5 Sterne' }).checked).toBe(true);
	await fireEvent.click(screen.getByRole('radio', { name: '4,0 Sterne' }));
	await fireEvent.click(screen.getByRole('button', { name: 'Bewerten' }));
	expect(api.saveRecipeRating).toHaveBeenLastCalledWith(1, 4);
	await screen.findByRole('button', { name: /4,0 von 5.*1 Bewertung/ });

	await fireEvent.click(trigger);
	await fireEvent.click(screen.getByRole('button', { name: 'Bewertung entfernen' }));
	expect(api.removeRecipeRating).toHaveBeenCalledWith(1);
	await screen.findByRole('button', { name: /Noch nicht bewertet/ });
	expect(screen.getByText('Bewertung entfernt.')).toBeTruthy();
});

test('a failed write retains the selection for retry and cancel leaves the average intact', async () => {
	auth.user = { id: 1, username: 'Lena', role: 'reader', is_active: true } as User;
	vi.mocked(api.saveRecipeRating).mockRejectedValue(new Error('offline'));
	render(RecipeRatings, { recipeId: 1 });
	const trigger = await screen.findByRole('button', { name: /5,0 von 5.*2 Bewertungen/ });
	await fireEvent.click(trigger);
	const choice = screen.getByRole<HTMLInputElement>('radio', { name: '3,5 Sterne' });
	await fireEvent.click(choice);
	const save = screen.getByRole<HTMLButtonElement>('button', { name: 'Bewerten' });
	await fireEvent.click(save);
	expect((await screen.findByRole('alert')).textContent).toBe('Bewertung konnte nicht gespeichert werden.');
	expect(choice.checked).toBe(true);
	expect(save.disabled).toBe(false);
	await fireEvent.click(screen.getByRole('button', { name: 'Abbrechen' }));
	expect(screen.queryByRole('dialog')).toBeNull();
	expect(trigger.getAttribute('aria-label')).toContain('5,0 von 5');
});
