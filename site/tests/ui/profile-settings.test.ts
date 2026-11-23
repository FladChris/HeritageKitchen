import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import * as api from '../../src/lib/api';
import { auth } from '../../src/lib/stores/auth.svelte';
import type { User } from '../../src/lib/types';
import Settings from '../../src/routes/account/settings/+page.svelte';
import VerifyEmail from '../../src/routes/verify-email/+page.svelte';
import { goto, page } from './navigation.svelte';

vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	emailAvailable: vi.fn(),
	getCurrentUser: vi.fn(),
	updateProfile: vi.fn(),
	changePassword: vi.fn(),
	verifyEmail: vi.fn(),
	setProfileImage: vi.fn(),
	removeProfileImage: vi.fn()
}));

vi.mock('cropperjs', () => ({
	default: class {
		destroy() {}
		getCroppedCanvas() {
			return { toBlob: (callback: BlobCallback) => callback(new Blob(['crop'])) };
		}
	}
}));

const user: User = {
	id: 1,
	username: 'lena',
	email_verified_at: null,
	email: 'lena@example.com',
	profile_image_path: null,
	role: 'reader',
	is_active: true,
	pending_approval: false,
	created_at: ''
};

beforeEach(() => {
	vi.resetAllMocks();
	vi.mocked(api.emailAvailable).mockResolvedValue({ available: true });
	vi.mocked(api.getCurrentUser).mockResolvedValue(user);
	auth.initialized = true;
	auth.user = user;
	goto('/account/settings');
});

afterEach(() => vi.unstubAllGlobals());

test('changes the username and requires matching email fields and password', async () => {
	vi.mocked(api.updateProfile)
		.mockResolvedValueOnce({ ...user, username: 'neuelena' })
		.mockResolvedValueOnce({ ...user, username: 'neuelena', email: 'neu@example.com' });
	render(Settings);
	const name = await screen.findByLabelText('Benutzername');
	await fireEvent.input(name, { target: { value: 'neuelena' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Username ändern' }));
	expect(api.updateProfile).toHaveBeenNthCalledWith(1, { username: 'neuelena' });
	await waitFor(() => expect(auth.user?.username).toBe('neuelena'));

	const email = screen.getByLabelText('E-Mail', { exact: true });
	const confirmation = screen.getByLabelText('E-Mail bestätigen');
	const password = screen.getByLabelText('Passwort zur Identifizierung');
	await fireEvent.input(email, { target: { value: 'neu@example.com' } });
	const save = screen.getByRole('button', { name: 'E-Mail ändern' });
	await fireEvent.input(password, { target: { value: 'supersecret123' } });
	await fireEvent.click(save);
	expect(api.updateProfile).toHaveBeenCalledTimes(1);
	await fireEvent.input(confirmation, { target: { value: 'neu@example.com' } });
	await fireEvent.click(save);
	expect(api.updateProfile).toHaveBeenNthCalledWith(2, {
		email: 'neu@example.com',
		current_password: 'supersecret123'
	});
	await waitFor(() => expect(auth.user?.email).toBe('neu@example.com'));
	expect(screen.getByText('Unbestätigt', { exact: false })).toBeTruthy();
});

test('disables email without SMTP and changes the password on the same page', async () => {
	vi.mocked(api.emailAvailable).mockResolvedValue({ available: false });
	vi.mocked(api.changePassword).mockResolvedValue();
	render(Settings);
	const email = await screen.findByLabelText<HTMLInputElement>('E-Mail', { exact: true });
	expect(email.disabled).toBe(true);
	expect(screen.getByText(/SMTP eingerichtet/)).toBeTruthy();
	expect(screen.getByText(/aktuelle Sitzung bleibt/)).toBeTruthy();
	await fireEvent.input(screen.getByLabelText('Altes Passwort'), {
		target: { value: 'old-password' }
	});
	await fireEvent.input(screen.getByLabelText('Neues Passwort', { exact: true }), {
		target: { value: 'new-password' }
	});
	await fireEvent.input(screen.getByLabelText('Neues Passwort wiederholen'), {
		target: { value: 'new-password' }
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Passwort ändern' }));
	expect(api.changePassword).toHaveBeenCalledWith('old-password', 'new-password');
	expect(await screen.findByText('Dein Passwort wurde geändert.')).toBeTruthy();
});

test('removes a stored email with a password while the address fields are disabled', async () => {
	vi.mocked(api.emailAvailable).mockResolvedValue({
		available: false,
		hint: 'Die Servereinstellung RESET_BASE_URL fehlt.'
	});
	vi.mocked(api.updateProfile).mockResolvedValue({ ...user, email: null });
	render(Settings);
	const hint = await screen.findByText(/RESET_BASE_URL/);
	const email = screen.getByLabelText<HTMLInputElement>('E-Mail', { exact: true });
	expect(email.disabled).toBe(true);
	expect(email.getAttribute('aria-describedby')).toBe(hint.id);
	expect(screen.getByLabelText<HTMLInputElement>('E-Mail bestätigen').disabled).toBe(true);
	const password = screen.getByLabelText<HTMLInputElement>('Passwort zur Identifizierung');
	expect(password.disabled).toBe(false);
	const remove = screen.getByRole('button', { name: 'E-Mail entfernen' });
	await fireEvent.click(remove);
	expect(api.updateProfile).not.toHaveBeenCalled();
	await fireEvent.input(password, { target: { value: 'supersecret123' } });
	await fireEvent.click(remove);
	expect(api.updateProfile).toHaveBeenCalledWith({ email: null, current_password: 'supersecret123' });
	expect(await screen.findByText('Deine E-Mail-Adresse wurde entfernt.')).toBeTruthy();
	expect(screen.queryByRole('button', { name: 'E-Mail entfernen' })).toBeNull();
	expect(password.disabled).toBe(true);
});

test('crops an image inside the profile dialog and saves or removes it explicitly', async () => {
	const first = '/media/recipe-images/profiles/1/first.jpg';
	vi.mocked(api.setProfileImage).mockResolvedValue({ ...user, profile_image_path: first });
	vi.mocked(api.removeProfileImage).mockResolvedValue(user);
	vi.stubGlobal(
		'Image',
		class {
			naturalWidth = 300;
			naturalHeight = 300;
			async decode() {}
		}
	);
	vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:profile-image');
	vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
	render(Settings);
	const edit = await screen.findByRole('button', { name: 'Profilbild bearbeiten' });
	await fireEvent.click(edit);
	const dialog = within(screen.getByRole('dialog', { name: 'Profilbild' }));
	expect(dialog.getByLabelText('Foto aufnehmen').getAttribute('capture')).toBe('user');
	const file = new File(['image'], 'profile.png', { type: 'image/png' });
	await fireEvent.change(dialog.getByLabelText('Bild hinzufügen'), { target: { files: [file] } });
	await dialog.findByAltText('Vorschau zum Zuschneiden');
	await fireEvent.click(dialog.getByRole('button', { name: 'Speichern' }));
	await waitFor(() => expect(auth.user?.profile_image_path).toBe(first));
	expect(api.setProfileImage).toHaveBeenCalledWith(expect.any(File));
	await fireEvent.click(edit);
	await fireEvent.click(screen.getByRole('button', { name: 'Bild entfernen' }));
	expect(api.removeProfileImage).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
	await waitFor(() => expect(auth.user?.profile_image_path).toBeNull());
});

test.each([
	['image/webp', 300, 'Erlaubt sind JPG und PNG.'],
	['image/png', 199, 'Das Bild muss mindestens 200 × 200 Pixel groß sein.']
])('loading an existing %s profile image retains the profile validation (%i pixels)', async (type, width, message) => {
	const path = '/media/recipe-images/profiles/1/existing.jpg';
	auth.user = { ...user, profile_image_path: path };
	vi.mocked(api.getCurrentUser).mockResolvedValue(auth.user);
	vi.stubGlobal('Image', class {
		naturalWidth = width;
		naturalHeight = 300;
		async decode() {}
	});
	vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:profile-image');
	vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
	const fetchImage = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('image', {
		headers: { 'Content-Type': type }
	}));
	render(Settings);
	await fireEvent.click(await screen.findByRole('button', { name: 'Profilbild bearbeiten' }));
	await fireEvent.click(screen.getByRole('button', { name: 'Bild zuschneiden' }));
	expect((await screen.findByRole('alert')).textContent).toBe(message);
	expect(fetchImage).toHaveBeenCalledExactlyOnceWith(path);
	expect(screen.queryByAltText('Vorschau zum Zuschneiden')).toBeNull();
	expect(api.setProfileImage).not.toHaveBeenCalled();
});

test('redirects visitors to login', async () => {
	auth.user = null;
	render(Settings);
	await waitFor(() => expect(page.url.pathname).toBe('/login'));
	expect(screen.queryByLabelText('Benutzername')).toBeNull();
});

test('redeems the verification link after the user confirms', async () => {
	goto('/verify-email?token=mail-token');
	vi.mocked(api.verifyEmail).mockResolvedValue();
	render(VerifyEmail);
	expect(api.verifyEmail).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByRole('button', { name: 'E-Mail bestätigen' }));
	expect(api.verifyEmail).toHaveBeenCalledWith('mail-token');
	expect(await screen.findByText('Deine E-Mail-Adresse wurde bestätigt.')).toBeTruthy();
});
