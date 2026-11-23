import { beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import RecipeComments from '../../src/lib/components/RecipeComments.svelte';
import * as api from '../../src/lib/api';
import type { RecipeComment, User } from '../../src/lib/types';

vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	listRecipeComments: vi.fn(),
	createRecipeComment: vi.fn(),
	updateRecipeComment: vi.fn(),
	deleteRecipeComment: vi.fn()
}));

const tim: User = {
	id: 1,
	username: 'Tim',
	email: null,
	email_verified_at: null,
	role: 'reader',
	is_active: true,
	pending_approval: false,
	created_at: ''
};
const first: RecipeComment = {
	id: 1,
	recipe_id: 7,
	author_id: tim.id,
	author_username: tim.username,
	text: 'Weniger Zucker.',
	created_at: '2026-11-16T15:30:00Z',
	edited_at: null
};
const second: RecipeComment = {
	...first,
	id: 2,
	author_id: null,
	author_username: null,
	text: '<b>Mit Zimt.</b>',
	created_at: '2026-11-18T15:30:00Z',
	edited_at: '2026-11-19T11:00:00Z'
};

beforeEach(() => {
	vi.mocked(api.listRecipeComments).mockResolvedValue([first, second]);
});

test('guests can read dates, authors and edit markers without write controls', async () => {
	render(RecipeComments, { recipeId: 7, user: null });
	const list = within(await screen.findByRole('list'));
	const [older, newer] = list.getAllByRole('listitem');
	expect(within(older).getByText('Tim')).toBeTruthy();
	expect(older.querySelector('time')?.dateTime).toBe(first.created_at);
	expect(within(older).queryByText(/^Bearbeitet von /)).toBeNull();
	expect(within(newer).getByText('Gelöschter Benutzer')).toBeTruthy();
	expect(within(newer).getByText(/^Bearbeitet von /)).toBeTruthy();
	expect(within(newer).getByText('<b>Mit Zimt.</b>')).toBeTruthy();
	expect(screen.queryByRole('textbox')).toBeNull();
	expect(screen.queryByRole('button')).toBeNull();
});

test('a reader can post, edit and delete their own comments', async () => {
	render(RecipeComments, { recipeId: 7, user: tim });
	await screen.findByText(first.text);
	const add = screen.getByRole('button', { name: 'Kommentar veröffentlichen' });
	const draft = screen.getByRole('textbox', { name: 'Dein Kommentar' });
	await fireEvent.input(draft, { target: { value: '   ' } });
	expect((add as HTMLButtonElement).disabled).toBe(true);

	const posted = { ...first, id: 3, text: 'Noch warm probieren.' };
	vi.mocked(api.createRecipeComment).mockResolvedValueOnce(posted);
	await fireEvent.input(draft, { target: { value: posted.text } });
	await fireEvent.click(add);
	await screen.findByText(posted.text);
	expect(api.createRecipeComment).toHaveBeenCalledWith(7, posted.text);

	const edited = { ...first, text: '50 g weniger Zucker.', edited_at: second.edited_at };
	vi.mocked(api.updateRecipeComment).mockResolvedValueOnce(edited);
	const own = screen.getByText(first.text).closest('li')!;
	const edit = within(own).getByRole('button', { name: 'Kommentar bearbeiten' });
	edit.focus();
	await fireEvent.click(edit);
	expect(document.activeElement).toBe(within(own).getByRole('textbox', { name: 'Kommentar bearbeiten' }));
	const cancel = within(own).getByRole('button', { name: 'Abbrechen' });
	cancel.focus();
	await fireEvent.click(cancel);
	const restored = within(own).getByRole('button', { name: 'Kommentar bearbeiten' });
	expect(document.activeElement).toBe(restored);
	await fireEvent.click(restored);
	await fireEvent.input(within(own).getByRole('textbox', { name: 'Kommentar bearbeiten' }), {
		target: { value: edited.text }
	});
	await fireEvent.click(within(own).getByRole('button', { name: 'Speichern' }));
	await within(own).findByText(edited.text);
	expect(within(own).getByText(/^Bearbeitet von /)).toBeTruthy();
	expect(own.querySelector('time')?.dateTime).toBe(first.created_at);
	expect(api.updateRecipeComment).toHaveBeenCalledWith(7, first.id, edited.text);

	vi.mocked(api.deleteRecipeComment).mockResolvedValueOnce();
	await fireEvent.click(within(own).getByRole('button', { name: 'Kommentar löschen' }));
	await waitFor(() => expect(document.activeElement).toBe(draft));
	expect(api.deleteRecipeComment).toHaveBeenCalledWith(7, first.id);
	expect(screen.queryByText(edited.text)).toBeNull();
	expect(within(screen.getByText(second.text).closest('li')!).queryByRole('button')).toBeNull();
});

test('an admin can delete but cannot edit a comment by another author', async () => {
	render(RecipeComments, { recipeId: 7, user: { ...tim, id: 3, role: 'admin' } });
	const item = within((await screen.findByText(first.text)).closest('li')!);
	expect(item.queryByRole('button', { name: 'Kommentar bearbeiten' })).toBeNull();
	vi.mocked(api.deleteRecipeComment).mockResolvedValueOnce();
	await fireEvent.click(item.getByRole('button', { name: 'Kommentar löschen' }));
	expect(api.deleteRecipeComment).toHaveBeenCalledWith(7, first.id);
	expect(screen.queryByText(first.text)).toBeNull();
});

test('a failed post retains the draft and adds no comment', async () => {
	render(RecipeComments, { recipeId: 7, user: tim });
	await screen.findByText(first.text);
	const draft = screen.getByRole('textbox', { name: 'Dein Kommentar' }) as HTMLTextAreaElement;
	vi.mocked(api.createRecipeComment).mockRejectedValueOnce(new TypeError('network error'));
	await fireEvent.input(draft, { target: { value: 'Mein Entwurf' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Kommentar veröffentlichen' }));
	expect(await screen.findByRole('alert')).toBeTruthy();
	expect(draft.value).toBe('Mein Entwurf');
	expect(screen.getAllByRole('listitem')).toHaveLength(2);
});
