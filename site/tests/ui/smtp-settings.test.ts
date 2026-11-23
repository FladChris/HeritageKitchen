import { beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import * as api from '../../src/lib/api';
import { auth } from '../../src/lib/stores/auth.svelte';
import type { SmtpSettings, User } from '../../src/lib/types';
import Settings from '../../src/routes/admin/settings/+page.svelte';
import ForgotPassword from '../../src/routes/forgot-password/+page.svelte';
import Users from '../../src/routes/users/+page.svelte';

vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	getSettings: vi.fn(),
	updateSettings: vi.fn(),
	getSmtpSettings: vi.fn(),
	updateSmtpSettings: vi.fn(),
	sendSmtpTest: vi.fn(),
	resetAvailable: vi.fn(),
	requestPasswordReset: vi.fn(),
	listUsers: vi.fn(),
	sendUserPasswordReset: vi.fn()
}));

const admin: User = {
	id: 1,
	username: 'petra',
	email: null,
	email_verified_at: null,
	role: 'admin',
	is_active: true,
	pending_approval: false,
	created_at: ''
};
const reader: User = {
	...admin,
	id: 2,
	username: 'tim',
	email: 'tim@example.com',
	email_verified_at: null,
	role: 'reader'
};
const configured: SmtpSettings = {
	version: 4,
	host: 'mail.example.com',
	port: 587,
	encryption: 'starttls',
	username: 'mail-user',
	sender: 'cookbook@example.com',
	has_password: true,
	status: 'tested',
	account_mail_hint: null
};

beforeEach(() => {
	vi.resetAllMocks();
	auth.user = admin;
	auth.initialized = true;
	vi.mocked(api.getSettings).mockResolvedValue({
		cookbook_name: 'Familienkochbuch',
		home_title: 'Lieblingsrezepte',
		home_tagline: '',
		footer_text: '',
	});
});

test('keeps the stored password blank and sends the draft before saving', async () => {
	const changed = { ...configured, sender: 'new@example.com', status: 'untested' } as const;
	const tested = { ...changed, status: 'tested' } as const;
	vi.mocked(api.getSmtpSettings).mockResolvedValue(configured);
	vi.mocked(api.updateSmtpSettings).mockResolvedValue(tested);
	vi.mocked(api.sendSmtpTest)
		.mockRejectedValueOnce(new api.ApiError(502, 'Der SMTP-Versand ist fehlgeschlagen.'))
		.mockResolvedValue(tested);
	render(Settings);

	const smtp = await screen.findByRole('region', { name: 'SMTP-Versand' });
	const form = within(smtp);
	const password = await form.findByLabelText<HTMLInputElement>('SMTP-Passwort');
	expect(password.value).toBe('');
	expect(form.getByRole('form', { name: 'Testversand' })).toBeTruthy();
	expect(document.getElementById(password.getAttribute('aria-describedby')!)?.textContent)
		.toContain('Leer lassen, um das gespeicherte Passwort zu behalten.');
	const toggle = form.getByRole('button', { name: 'Passwort anzeigen' });
	expect(toggle.querySelector('path')?.getAttribute('d')).toContain('M3 19');
	await fireEvent.click(toggle);
	expect(password.type).toBe('text');
	expect(toggle.querySelector('path')?.getAttribute('d')).toContain('M3 13');
	await fireEvent.click(toggle);
	expect(password.type).toBe('password');
	expect(form.getByText('Erfolgreich getestet')).toBeTruthy();
	await fireEvent.input(form.getByLabelText('Absenderadresse'), {
		target: { value: changed.sender }
	});
	await fireEvent.input(password, { target: { value: 'new password' } });
	const draft = {
		version: configured.version,
		host: configured.host,
		port: configured.port,
		encryption: configured.encryption,
		username: configured.username,
		sender: changed.sender,
		password: 'new password'
	};

	await fireEvent.input(form.getByLabelText('Empfängeradresse'), {
		target: { value: 'petra@example.com' }
	});
	const send = form.getByRole('button', { name: 'Test-E-Mail senden' });
	await fireEvent.click(send);
	expect(await form.findByText('Der SMTP-Versand ist fehlgeschlagen.')).toBeTruthy();
	expect(password.value).toBe(draft.password);
	await fireEvent.click(send);
	expect(api.sendSmtpTest).toHaveBeenLastCalledWith('petra@example.com', draft);
	expect(await form.findByText(/Der SMTP-Server hat die Test-E-Mail angenommen/)).toBeTruthy();
	expect(api.updateSmtpSettings).not.toHaveBeenCalled();
	expect(password.value).toBe(draft.password);

	await fireEvent.click(form.getByRole('button', { name: 'SMTP-Einstellungen speichern' }));
	expect(api.updateSmtpSettings).toHaveBeenCalledWith(draft);
	expect(await form.findByText('SMTP-Einstellungen gespeichert.')).toBeTruthy();
	expect(form.getByText('Erfolgreich getestet')).toBeTruthy();
	expect(password.value).toBe('');
});

test('fills SMTP presets, shows provider guidance and follows the username until overridden', async () => {
	vi.mocked(api.getSmtpSettings).mockResolvedValue({
		...configured, host: '', username: '', sender: '', has_password: false, status: 'not_configured'
	});
	render(Settings);
	const provider = await screen.findByLabelText<HTMLSelectElement>('Anbieter');
	const host = screen.getByLabelText<HTMLInputElement>('SMTP-Server');
	const port = screen.getByLabelText<HTMLInputElement>('Port');
	const encryption = screen.getByLabelText<HTMLSelectElement>('Verschlüsselung');
	const username = screen.getByLabelText<HTMLInputElement>('SMTP-Benutzername (optional)');
	const sender = screen.getByLabelText<HTMLInputElement>('Absenderadresse');
	expect(provider.value).toBe('custom');
	expect(screen.getByRole('button', { name: 'Test-E-Mail senden' })).toBeTruthy();

	for (const [value, hostname, domain] of [
		['gmx', 'mail.gmx.net', 'gmx.de'],
		['webde', 'smtp.web.de', 'web.de'],
		['gmail', 'smtp.gmail.com', 'gmail.com']
	]) {
		await fireEvent.change(provider, { target: { value } });
		expect([host.value, port.value, encryption.value]).toEqual([hostname, '587', 'starttls']);
		expect(username.placeholder).toBe(`name@${domain}`);
		expect(sender.placeholder).toBe(username.placeholder);
		expect(screen.getByText(/als Absender nur die eigene E-Mail-Adresse/)).toBeTruthy();
		if (value !== 'gmail') expect(screen.getByText(/POP3\/IMAP-Zugriff erlauben/)).toBeTruthy();
	}
	expect(screen.getByRole('link', { name: 'App-Passwort' }).getAttribute('href')).toBe(
		'https://myaccount.google.com/apppasswords'
	);
	expect(screen.getByLabelText<HTMLInputElement>('SMTP-Passwort').placeholder).toBe('App-Passwort');
	await fireEvent.input(username, { target: { value: 'reader@example.com' } });
	expect(sender.value).toBe('reader@example.com');
	await fireEvent.input(sender, { target: { value: 'kochbuch@example.com' } });
	await fireEvent.input(username, { target: { value: 'other@example.com' } });
	expect(sender.value).toBe('kochbuch@example.com');

	await fireEvent.change(provider, { target: { value: 'custom' } });
	expect([host.value, port.value, encryption.value]).toEqual(['smtp.gmail.com', '587', 'starttls']);
	await fireEvent.change(provider, { target: { value: 'gmail' } });
	await fireEvent.input(port, { target: { value: '465' } });
	expect(provider.value).toBe('custom');
	expect(port.value).toBe('465');
});

test('recognizes the provider of stored SMTP settings by hostname', async () => {
	vi.mocked(api.getSmtpSettings).mockResolvedValue({ ...configured, host: 'SMTP.WEB.DE' });
	render(Settings);
	expect((await screen.findByLabelText<HTMLSelectElement>('Anbieter')).value).toBe('webde');
});

test('does not load SMTP settings for an editor', async () => {
	auth.user = { ...admin, role: 'editor' };
	render(Settings);
	await waitFor(() => expect(screen.queryByText('SMTP-Versand')).toBeNull());
	expect(api.getSmtpSettings).not.toHaveBeenCalled();
});

test('shows a missing link base separately from successful SMTP testing', async () => {
	const result = { ...configured, account_mail_hint: 'Die Servereinstellung RESET_BASE_URL fehlt.' };
	vi.mocked(api.getSmtpSettings).mockResolvedValue(result);
	render(Settings);
	const smtp = within(await screen.findByRole('region', { name: 'SMTP-Versand' }));
	expect(await smtp.findByText(/RESET_BASE_URL/)).toBeTruthy();
	expect(smtp.getByText('Erfolgreich getestet')).toBeTruthy();
});

test('removes SMTP after confirmation and shows its new status', async () => {
	vi.mocked(api.getSmtpSettings).mockResolvedValue(configured);
	vi.mocked(api.updateSmtpSettings).mockResolvedValue({
		...configured,
		host: '',
		sender: '',
		username: '',
		has_password: false,
		status: 'not_configured'
	});
	render(Settings);
	await fireEvent.click(
		await screen.findByRole('button', { name: 'SMTP-Einstellungen entfernen' })
	);
	const dialog = within(screen.getByRole('dialog', { name: 'SMTP-Einstellungen entfernen?' }));
	expect(api.updateSmtpSettings).not.toHaveBeenCalled();
	await fireEvent.click(dialog.getByRole('button', { name: 'Entfernen' }));
	expect(api.updateSmtpSettings).toHaveBeenCalledWith(
		expect.objectContaining({
			version: configured.version,
			host: '',
			sender: '',
			username: '',
			password: ''
		})
	);
	expect(await screen.findByText('Nicht eingerichtet')).toBeTruthy();
});

test('offers only the admin contact when email reset is unavailable', async () => {
	vi.mocked(api.resetAvailable).mockResolvedValue({ available: false });
	render(ForgotPassword);
	expect(await screen.findByText('Bitte wende dich an einen Admin.')).toBeTruthy();
	expect(screen.queryByRole('button', { name: 'Link anfordern' })).toBeNull();
});

test('acknowledges a public reset request without claiming mail was sent', async () => {
	vi.mocked(api.resetAvailable).mockResolvedValue({ available: true });
	vi.mocked(api.requestPasswordReset).mockResolvedValue();
	render(ForgotPassword);
	const email = await screen.findByLabelText('E-Mail');
	await fireEvent.input(email, { target: { value: 'tim@example.com' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Link anfordern' }));
	expect(await screen.findByText('Deine Anfrage wurde entgegengenommen.')).toBeTruthy();
	expect(api.requestPasswordReset).toHaveBeenCalledWith('tim@example.com');
});

test.each(['zip', 'pdf'] as const)('the cookbook %s export downloads a named file and removes the link', async (format) => {
	vi.mocked(api.getSmtpSettings).mockResolvedValue(configured);
	const fetchExport = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('export'));
	vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:cookbook-export');
	vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
	let download: { name: string; href: string; connected: boolean } | undefined;
	const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
		download = { name: this.download, href: this.href, connected: this.isConnected };
	});
	render(Settings);
	const name = format === 'zip' ? 'JSON-ZIP herunterladen' : 'Gesamt-PDF herunterladen';
	await fireEvent.click(await screen.findByRole('button', { name }));
	await waitFor(() => expect(click).toHaveBeenCalledOnce());
	expect(download).toEqual({
		name: 'heritagekitchen-cookbook.' + format,
		href: 'blob:cookbook-export',
		connected: true
	});
	expect(fetchExport).toHaveBeenCalledExactlyOnceWith('/api/settings/export/' + format, {
		credentials: 'include', cache: 'no-store'
	});
	expect(document.querySelector('a[download]')).toBeNull();
});

test.each([
	[false, true],
	[true, false],
	[true, true]
])(
	'offers admin reset mail only when available and verified (%s, %s)',
	async (available, verified) => {
		vi.mocked(api.listUsers).mockResolvedValue([
			admin,
			{ ...reader, email_verified_at: verified ? '2026-11-22T12:00:00' : null }
		]);
		vi.mocked(api.resetAvailable).mockResolvedValue({ available });
		vi.mocked(api.sendUserPasswordReset).mockResolvedValue();
		render(Users);
		const row = within(await screen.findByRole('row', { name: /tim@example.com/ }));
		expect(row.getByRole('button', { name: 'Passwort setzen' })).toBeTruthy();
		const send = row.queryByRole('button', { name: 'Reset-Link senden' });
		expect(row.getByText(available && verified ? 'Bestätigt' : 'Unbestätigt')).toBeTruthy();
		if (available && verified) {
			expect(send).toBeTruthy();
			await fireEvent.click(send!);
			expect(api.sendUserPasswordReset).toHaveBeenCalledWith(reader.id);
			expect(
				await screen.findByText('Der SMTP-Server hat die Reset-E-Mail angenommen.')
			).toBeTruthy();
		} else {
			expect(send).toBeNull();
		}
	}
);

test.each([
	['JSON-ZIP herunterladen', 'zip', 'Erstellt ZIP …'],
	['Gesamt-PDF herunterladen', 'pdf', 'Erstellt PDF …']
])(
	'the export button %s retains focus and announces progress and errors',
	async (name, format, pending) => {
		vi.mocked(api.getSmtpSettings).mockResolvedValue(configured);
		let finish!: (response: Response) => void;
		const fetchExport = vi.fn(() => new Promise<Response>((resolve) => (finish = resolve)));
		vi.stubGlobal('fetch', fetchExport);
		try {
			render(Settings);
			const section = within(
				await screen.findByRole('region', { name: 'Gesamtes Kochbuch exportieren' })
			);
			expect(
				section.getByText(/^Der ZIP-Export enthält/).textContent
			).toContain('Der ZIP-Export enthält Rezepte, Kategorien, Bilder, Kommentare und Bewertungen.');
			const status = section.getByRole('status');
			const button = section.getByRole('button', { name });
			expect(button.tabIndex).toBe(0);
			button.focus();
			await fireEvent.click(button);
			expect(fetchExport).toHaveBeenCalledWith('/api/settings/export/' + format, expect.anything());
			expect(status.textContent).toBe(pending);
			expect(section.getByRole('button', { name }).getAttribute('aria-disabled')).toBe('true');
			await fireEvent.click(button);
			expect(fetchExport).toHaveBeenCalledOnce();
			finish(new Response('', { status: 403 }));
			expect((await section.findByRole('alert')).textContent).toContain('Nur Administratoren');
			expect(status.textContent?.trim()).toBe('');
			expect(document.activeElement).toBe(button);
		} finally {
			vi.unstubAllGlobals();
		}
	}
);
