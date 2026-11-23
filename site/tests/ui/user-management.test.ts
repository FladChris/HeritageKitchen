import { beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import * as api from '../../src/lib/api';
import { auth } from '../../src/lib/stores/auth.svelte';
import { offline } from '../../src/lib/stores/offline.svelte';
import type { User, UserRole } from '../../src/lib/types';
import Users from '../../src/routes/users/+page.svelte';
import { goto, page } from './navigation.svelte';

vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	listUsers: vi.fn(),
	resetAvailable: vi.fn(),
	getCurrentUser: vi.fn(),
	createUser: vi.fn(),
	updateUser: vi.fn(),
	deleteUser: vi.fn()
}));

const admin: User = {
	id: 1,
	username: 'petra',
	email: 'petra@example.com',
	email_verified_at: null,
	role: 'admin',
	is_active: true,
	pending_approval: false,
	created_at: ''
};
const second: User = { ...admin, id: 2, username: 'lena', email: null };

beforeEach(() => {
	vi.resetAllMocks();
	goto('/users');
	offline.markConnection(false);
	auth.user = admin;
	auth.initialized = true;
	auth.loading = false;
	vi.mocked(api.listUsers).mockResolvedValue([admin, second]);
	vi.mocked(api.resetAvailable).mockResolvedValue({ available: false });
});

test('explains missing email link configuration in the account creation form', async () => {
	vi.mocked(api.resetAvailable).mockResolvedValue({
		available: false,
		hint: 'Die Servereinstellung RESET_BASE_URL fehlt.'
	});
	render(Users);
	await fireEvent.click(screen.getByRole('button', { name: 'Neuer Benutzer' }));
	const hint = await screen.findByText(/RESET_BASE_URL/);
	const email = screen.getByLabelText<HTMLInputElement>('E-Mail (optional)');
	expect(email.disabled).toBe(true);
	expect(email.getAttribute('aria-describedby')).toBe(hint.id);
});

test.each<UserRole>(['reader', 'editor'])('hides user management from a %s', async (role) => {
	auth.user = { ...admin, role };
	render(Users);
	expect(screen.queryByRole('button', { name: 'Neuer Benutzer' })).toBeNull();
	await waitFor(() => expect(page.url.pathname).toBe('/'));
	expect(api.listUsers).not.toHaveBeenCalled();
});

test('shows user fields and allows an admin to give up her own role', async () => {
	const demoted: User = { ...admin, role: 'editor' };
	vi.mocked(api.updateUser).mockResolvedValue(demoted);
	vi.mocked(api.getCurrentUser).mockResolvedValue(demoted);
	render(Users);
	const ownRow = await screen.findByRole('row', { name: /petra.*petra@example.com.*Unbestätigt/ });
	const role = within(ownRow).getByRole('combobox', {
		name: 'Rolle von petra'
	}) as HTMLSelectElement;
	expect(role.value).toBe('admin');
	expect(role.disabled).toBe(false);
	await fireEvent.change(role, { target: { value: 'editor' } });
	expect(api.updateUser).toHaveBeenCalledWith(admin.id, { role: 'editor' });
	await waitFor(() => expect(page.url.pathname).toBe('/'));
	expect(auth.user?.role).toBe('editor');
	expect(screen.queryByRole('button', { name: 'Neuer Benutzer' })).toBeNull();
	expect(api.listUsers).toHaveBeenCalledTimes(1);
});

test('restores the role selection when the server rejects loss of the last active admin', async () => {
	const message = 'Mindestens ein Administratorkonto muss aktiv bleiben.';
	vi.mocked(api.updateUser).mockRejectedValue(new api.ApiError(409, message));
	render(Users);
	const role = (await screen.findByRole('combobox', {
		name: 'Rolle von petra'
	})) as HTMLSelectElement;
	await fireEvent.change(role, { target: { value: 'reader' } });
	expect((await screen.findByRole('alert')).textContent).toBe(message);
	expect(role.value).toBe('admin');
});

test('protects the last active administrator in the user list', async () => {
	vi.mocked(api.listUsers).mockResolvedValue([admin, { ...second, is_active: false }]);
	render(Users);
	const ownRow = await screen.findByRole('row', { name: /petra/ });
	const role = within(ownRow).getByRole('combobox', {
		name: 'Rolle von petra'
	}) as HTMLSelectElement;
	const deactivate = within(ownRow).getByRole('button', {
		name: 'Deaktivieren'
	}) as HTMLButtonElement;
	expect(role.disabled).toBe(true);
	expect(deactivate.disabled).toBe(true);
	const remove = within(ownRow).getByRole<HTMLButtonElement>('button', { name: 'Benutzer löschen' });
	expect(remove.disabled).toBe(true);
});

async function openDeleteDialog() {
	const row = await screen.findByRole('row', { name: /lena/i });
	await fireEvent.click(within(row).getByRole('button', { name: 'Benutzer löschen' }));
	return screen.getByRole('dialog', { name: 'Benutzer löschen?' });
}

test('deletes another account only after confirmation and explains the consequences', async () => {
	vi.mocked(api.listUsers).mockResolvedValueOnce([admin, second]).mockResolvedValue([admin]);
	render(Users);
	let dialog = await openDeleteDialog();
	expect(dialog.textContent).toContain('Gelöschter Benutzer');
	expect(dialog.textContent).toMatch(/Rezepte.*bleiben/s);
	expect(dialog.textContent).toContain('Persönliche Daten');
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Abbrechen' }));
	expect(api.deleteUser).not.toHaveBeenCalled();
	dialog = await openDeleteDialog();
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Endgültig löschen' }));
	expect(api.deleteUser).toHaveBeenCalledExactlyOnceWith(second.id);
	await waitFor(() => expect(screen.queryByRole('row', { name: /lena/i })).toBeNull());
});

test('explains when the server rejects deletion of the last active administrator', async () => {
	const message = 'Mindestens ein Administratorkonto muss aktiv bleiben.';
	vi.mocked(api.deleteUser).mockRejectedValue(new api.ApiError(409, message));
	render(Users);
	const dialog = await openDeleteDialog();
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Endgültig löschen' }));
	expect((await screen.findByRole('alert')).textContent).toBe(message);
	expect(screen.getByRole('row', { name: /lena/i })).toBeTruthy();
});

test('leaves user management after deleting the signed-in admin with another active admin', async () => {
	vi.mocked(api.getCurrentUser).mockRejectedValue(new api.ApiError(401, 'Melde dich an.'));
	render(Users);
	const row = await screen.findByRole('row', { name: /petra/ });
	await fireEvent.click(within(row).getByRole('button', { name: 'Benutzer löschen' }));
	const dialog = screen.getByRole('dialog', { name: 'Benutzer löschen?' });
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Endgültig löschen' }));
	expect(api.deleteUser).toHaveBeenCalledExactlyOnceWith(admin.id);
	await waitFor(() => expect(page.url.pathname).toBe('/'));
	expect(auth.user).toBeNull();
});

test('creates an account with a username and role while email is disabled', async () => {
	vi.mocked(api.createUser).mockResolvedValue(second);
	render(Users);
	await fireEvent.click(screen.getByRole('button', { name: 'Neuer Benutzer' }));
	await fireEvent.input(screen.getByLabelText('Benutzername'), { target: { value: 'lena' } });
	expect(screen.getByLabelText<HTMLInputElement>('E-Mail (optional)').disabled).toBe(true);
	expect(screen.getByText(/SMTP eingerichtet und getestet/)).toBeTruthy();
	await fireEvent.input(screen.getByLabelText('Passwort'), { target: { value: 'supersecret123' } });
	await fireEvent.change(screen.getByLabelText('Rolle'), { target: { value: 'admin' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Benutzer anlegen' }));
	expect(api.createUser).toHaveBeenCalledWith({
		username: 'lena',
		password: 'supersecret123',
		role: 'admin',
		email: null
	});
});
