import { beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import * as api from '../../src/lib/api';
import { auth } from '../../src/lib/stores/auth.svelte';
import type { User } from '../../src/lib/types';
import Login from '../../src/routes/login/+page.svelte';
import Register from '../../src/routes/register/+page.svelte';
import Users from '../../src/routes/users/+page.svelte';
import { goto, page } from './navigation.svelte';

vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	registrationStatus: vi.fn(),
	register: vi.fn(),
	login: vi.fn(),
	resetAvailable: vi.fn(),
	emailAvailable: vi.fn(),
	listUsers: vi.fn(),
	updateUser: vi.fn(),
	rejectRegistration: vi.fn()
}));

const admin: User = {
	id: 1,
	username: 'chefmax',
	email: null,
	email_verified_at: null,
	role: 'admin',
	is_active: true,
	pending_approval: false,
	created_at: ''
};
const pending: User = {
	...admin,
	id: 2,
	username: 'secondchef',
	role: 'editor',
	is_active: false,
	pending_approval: true
};

beforeEach(() => {
	vi.resetAllMocks();
	goto('/');
	auth.user = null;
	auth.initialized = true;
	vi.mocked(api.resetAvailable).mockResolvedValue({ available: false });
	vi.mocked(api.emailAvailable).mockResolvedValue({ available: false });
});

const firstAccountHint = 'Das erste Konto erhält automatisch die Rolle „Administrator“.';
const approvalHint = 'Dein Konto muss von einem Administrator freigeschaltet werden.';
const emailHint = 'E-Mail ist erst verfügbar, wenn SMTP eingerichtet und getestet ist.';
const pendingConfirmation = `Konto erstellt. ${approvalHint}`;

test('signs in with an email and toggles the password without losing the input', async () => {
	vi.mocked(api.login).mockResolvedValue(admin);
	vi.mocked(api.resetAvailable).mockResolvedValue({ available: true });
	goto('/login');
	render(Login);
	const identifier = await screen.findByLabelText('Benutzername oder E-Mail-Adresse');
	const password = screen.getByLabelText<HTMLInputElement>('Passwort', { exact: true });
	await fireEvent.input(identifier, { target: { value: 'Chef@Example.com' } });
	await fireEvent.input(password, { target: { value: 'supersecret123' } });
	const toggle = screen.getByRole<HTMLButtonElement>('button', { name: 'Passwort anzeigen' });
	toggle.focus();
	expect(document.activeElement).toBe(toggle);
	expect(toggle.type).toBe('button');
	expect(toggle.querySelector('path')?.getAttribute('d')).toContain('M3 19');
	await fireEvent.click(toggle, { detail: 0 });
	expect(password.type).toBe('text');
	expect(password.value).toBe('supersecret123');
	expect(toggle.querySelector('path')?.getAttribute('d')).toContain('M3 13');
	await fireEvent.click(screen.getByRole('button', { name: 'Passwort verbergen' }), { detail: 0 });
	expect(password.type).toBe('password');
	expect(password.value).toBe('supersecret123');
	await fireEvent.click(screen.getByRole('button', { name: 'Anmelden' }));
	expect(api.login).toHaveBeenCalledWith('Chef@Example.com', 'supersecret123');
	await waitFor(() => expect(page.url.pathname).toBe('/'));
});

test.each([
	{
		user: admin,
		firstAccount: true,
		status: '1',
		confirmation: 'Konto erstellt – du kannst dich jetzt anmelden.'
	},
	{ user: pending, firstAccount: false, status: 'pending', confirmation: pendingConfirmation },
	{ user: pending, firstAccount: true, status: 'pending', confirmation: pendingConfirmation }
])(
	'shows the appropriate hints ($user.role result, first account hint: $firstAccount)',
	async ({ user, firstAccount, status, confirmation }) => {
		vi.mocked(api.registrationStatus).mockResolvedValue({ first_account: firstAccount });
		vi.mocked(api.register).mockResolvedValue(user);
		const registration = render(Register);
		expect(screen.queryByText(firstAccountHint)).toBeNull();
		expect(await screen.findByText(firstAccount ? firstAccountHint : approvalHint)).toBeTruthy();
		expect(screen.queryByText(firstAccount ? approvalHint : firstAccountHint)).toBeNull();
		const email = screen.getByLabelText<HTMLInputElement>('E-Mail (optional)');
		const resetHint = screen.getByText(emailHint);
		expect(email.required).toBe(false);
		expect(email.disabled).toBe(true);
		expect(email.nextElementSibling).toBe(resetHint);
		expect(email.getAttribute('aria-describedby')).toBe(resetHint.id);
		const username = screen.getByLabelText<HTMLInputElement>('Benutzername');
		expect(username.required).toBe(true);
		expect(username.maxLength).toBe(32);

		await fireEvent.input(username, { target: { value: user.username } });
		await fireEvent.input(screen.getByLabelText('Passwort'), {
			target: { value: 'supersecret123' }
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Konto erstellen' }));
		expect(api.register).toHaveBeenCalledWith({
			username: user.username,
			email: null,
			password: 'supersecret123'
		});
		await waitFor(() => expect(page.url.search).toBe(`?registered=${status}`));
		registration.unmount();
		render(Login);
		expect(screen.getByText(confirmation)).toBeTruthy();
	}
);

test('accepts an optional email for registration when SMTP is available', async () => {
	const email = 'chef@example.com';
	vi.mocked(api.registrationStatus).mockResolvedValue({ first_account: false });
	vi.mocked(api.emailAvailable).mockResolvedValue({ available: true });
	vi.mocked(api.register).mockResolvedValue({ ...pending, email });
	render(Register);
	await screen.findByText(approvalHint);
	const input = screen.getByLabelText<HTMLInputElement>('E-Mail (optional)');
	expect(input.disabled).toBe(false);
	await fireEvent.input(input, { target: { value: email } });
	await fireEvent.input(screen.getByLabelText('Benutzername'), {
		target: { value: pending.username }
	});
	await fireEvent.input(screen.getByLabelText('Passwort'), { target: { value: 'supersecret123' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Konto erstellen' }));
	expect(api.register).toHaveBeenCalledWith({
		username: pending.username,
		email,
		password: 'supersecret123'
	});
	await waitFor(() => expect(page.url.search).toBe('?registered=pending&confirmEmail=1'));
});

test('explains why email is disabled after SMTP has been tested', async () => {
	vi.mocked(api.registrationStatus).mockResolvedValue({ first_account: false });
	vi.mocked(api.emailAvailable).mockResolvedValue({
		available: false,
		hint: 'Die Servereinstellung RESET_BASE_URL fehlt.'
	});
	render(Register);
	const hint = await screen.findByText(/RESET_BASE_URL/);
	const email = screen.getByLabelText<HTMLInputElement>('E-Mail (optional)');
	expect(email.disabled).toBe(true);
	expect(email.getAttribute('aria-describedby')).toBe(hint.id);
});

test('admin can approve a pending account and distinguish it from a disabled account', async () => {
	const disabled = { ...pending, id: 3, username: 'disabledchef', pending_approval: false };
	const approved = { ...pending, is_active: true, pending_approval: false };
	auth.user = admin;
	vi.mocked(api.listUsers).mockResolvedValueOnce([admin, pending, disabled]);
	vi.mocked(api.listUsers).mockResolvedValueOnce([admin, approved, disabled]);
	vi.mocked(api.updateUser).mockResolvedValue(approved);
	render(Users);

	const pendingRow = await screen.findByRole('row', { name: /secondchef/ });
	const disabledRow = screen.getByRole('row', { name: /disabledchef/ });
	expect(within(pendingRow).getByText('Wartet auf Freischaltung')).toBeTruthy();
	expect(within(disabledRow).getByText('Deaktiviert')).toBeTruthy();
	expect(within(disabledRow).getByRole('button', { name: 'Aktivieren' })).toBeTruthy();
	await fireEvent.click(within(pendingRow).getByRole('button', { name: 'Freischalten' }));
	expect(api.updateUser).toHaveBeenCalledWith(pending.id, { is_active: true });
	const approvedRow = await screen.findByRole('row', { name: /secondchef.*Deaktivieren/ });
	const role = within(approvedRow).getByRole<HTMLSelectElement>('combobox', {
		name: 'Rolle von secondchef'
	});
	expect(role.value).toBe('editor');
	expect(role.selectedOptions[0]?.textContent).toBe('Redakteur');
	await waitFor(() => expect(role.disabled).toBe(false));
});

test('admin can reject only pending accounts after confirming permanent deletion', async () => {
	const disabled = { ...pending, id: 3, username: 'disabledchef', pending_approval: false };
	auth.user = admin;
	vi.mocked(api.listUsers).mockResolvedValueOnce([admin, pending, disabled]);
	vi.mocked(api.listUsers).mockResolvedValueOnce([admin, disabled]);
	vi.mocked(api.rejectRegistration).mockResolvedValue(undefined);
	render(Users);

	const pendingRow = await screen.findByRole('row', { name: /secondchef/ });
	const reject = within(pendingRow).getByRole('button', { name: 'Ablehnen' });
	for (const username of [admin.username, disabled.username]) {
		const row = screen.getByRole('row', { name: new RegExp(username) });
		expect(within(row).queryByRole('button', { name: 'Ablehnen' })).toBeNull();
	}

	await fireEvent.click(reject);
	const dialog = await screen.findByRole('dialog', { name: 'Registrierung ablehnen?' });
	expect(within(dialog).getByText(/secondchef.*endgültig gelöscht/)).toBeTruthy();
	expect(api.rejectRegistration).not.toHaveBeenCalled();
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Abbrechen' }));
	expect(screen.queryByRole('dialog')).toBeNull();
	expect(api.rejectRegistration).not.toHaveBeenCalled();

	await fireEvent.click(reject);
	const confirmation = await screen.findByRole('dialog');
	await fireEvent.click(within(confirmation).getByRole('button', { name: 'Endgültig ablehnen' }));
	expect(api.rejectRegistration).toHaveBeenCalledWith(pending.id);
	await waitFor(() => expect(screen.queryByRole('row', { name: /secondchef/ })).toBeNull());
	expect(screen.queryByRole('dialog')).toBeNull();
	expect(await screen.findByRole('row', { name: /disabledchef/ })).toBeTruthy();
});
