import { beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import Header from '../../src/lib/components/Header.svelte';
import { auth } from '../../src/lib/stores/auth.svelte';
import type { UserRole } from '../../src/lib/types';
import { offline } from '../../src/lib/stores/offline.svelte';
import { tick } from 'svelte';
import * as api from '../../src/lib/api';

vi.mock('../../src/lib/api', async (original) => ({
	...(await original<object>()),
	logout: vi.fn().mockResolvedValue(undefined)
}));

beforeEach(() => {
	auth.loading = false;
	offline.offline = false;
	offline.incomplete = false;
	offline.syncing = false;
	offline.syncError = null;
	offline.statusUserId = null;
	offline.lastCompleteSync = null;
});

function renderHeader(role: UserRole, profileImage: string | null = null) {
	auth.user = {
		id: 1,
		username: 'koch',
		email: null,
		email_verified_at: null,
		profile_image_path: profileImage,
		role,
		is_active: true,
		pending_approval: false,
		created_at: ''
	};
	render(Header);
	return screen.getByRole('button', { name: 'koch' });
}

test.each<UserRole>(['reader', 'editor', 'admin'])(
	'preserves account actions for %s',
	async (role) => {
		const trigger = renderHeader(role);
		expect(trigger.getAttribute('aria-expanded')).toBe('false');
		expect(screen.queryByRole('link', { name: 'Einstellungen', exact: true })).toBeNull();
		await fireEvent.click(trigger);
		expect(trigger.getAttribute('aria-expanded')).toBe('true');
		const personal = within(screen.getByRole('group', { name: 'Mein Konto' }));
		expect(
			personal.getByRole('link', { name: 'Einstellungen', exact: true }).getAttribute('href')
		).toBe('/account/settings');
		const navigation = within(screen.getByRole('navigation', { name: 'Hauptnavigation' }));
		expect(navigation.getByRole('link', { name: 'Rezepte' })).toBeTruthy();
		expect(navigation.getByRole('link', { name: 'Meine Favoriten' }).getAttribute('href')).toBe(
			'/favorites'
		);
		expect(trigger.querySelector('img')).toBeNull();
		expect(Boolean(screen.queryByRole('link', { name: 'Neues Rezept' }))).toBe(role !== 'reader');
		if (role === 'admin') {
			const admin = within(screen.getByRole('group', { name: 'Administration' }));
			expect(admin.getByRole('link', { name: 'Kochbuch-Einstellungen' }).getAttribute('href')).toBe(
				'/admin/settings'
			);
			expect(admin.getByRole('link', { name: 'Benutzerverwaltung' }).getAttribute('href')).toBe(
				'/users'
			);
		} else {
			expect(screen.queryByRole('link', { name: 'Kochbuch-Einstellungen' })).toBeNull();
			expect(screen.queryByRole('link', { name: 'Benutzerverwaltung' })).toBeNull();
		}
		await fireEvent.click(screen.getByRole('button', { name: 'Abmelden' }));
		expect(api.logout).toHaveBeenCalled();
		expect(screen.getByRole('link', { name: 'Anmelden' })).toBeTruthy();
	}
);

test('Escape closes the account menu and restores focus', async () => {
	const trigger = renderHeader('reader');
	await fireEvent.click(trigger);
	const settings = screen.getByRole('link', { name: 'Einstellungen', exact: true });
	settings.focus();
	await fireEvent.keyDown(settings, { key: 'Escape' });
	expect(document.activeElement).toBe(trigger);
	expect(trigger.getAttribute('aria-expanded')).toBe('false');
});

test('mobile navigation is labelled and Escape closes it with focus recovery', async () => {
	 renderHeader('reader');
	 const button = screen.getByRole('button', { name: 'Menü öffnen' });
	 expect(button.getAttribute('aria-controls')).toBe('primary-navigation');
	 await fireEvent.click(button);
	 expect(button.getAttribute('aria-expanded')).toBe('true');
	 const navigation = document.getElementById('primary-navigation');
	 expect(navigation?.classList.contains('open')).toBe(true);
	 await fireEvent.keyDown(screen.getByRole('link', { name: 'Rezepte' }), { key: 'Escape' });
	 expect(button.getAttribute('aria-expanded')).toBe('false');
	 expect(document.activeElement).toBe(button);
});

test('shows the profile image alongside the username', () => {
	const path = '/media/recipe-images/profiles/1/avatar.jpg';
	const trigger = renderHeader('reader', path);
	expect(trigger.querySelector('img')?.getAttribute('src')).toBe(path);
});

test('outside clicks and closing mobile navigation dismiss the account menu', async () => {
	const trigger = renderHeader('admin');
	await fireEvent.click(screen.getByRole('button', { name: 'Menü öffnen' }));
	await fireEvent.click(trigger);
	await fireEvent.click(document.body);
	expect(trigger.getAttribute('aria-expanded')).toBe('false');
	await fireEvent.click(trigger);
	await fireEvent.click(screen.getByRole('button', { name: 'Menü schließen' }));
	await fireEvent.click(screen.getByRole('button', { name: 'Menü öffnen' }));
	expect(trigger.getAttribute('aria-expanded')).toBe('false');
});

test('Escape stays available to an open native dialog', async () => {
	renderHeader('reader');
	const nav = screen.getByRole('button', { name: 'Menü öffnen' });
	await fireEvent.click(nav);
	const dialog = document.createElement('dialog');
	document.body.append(dialog);
	try {
		dialog.showModal();
		expect(await fireEvent.keyDown(dialog, { key: 'Escape' })).toBe(true);
		expect(nav.getAttribute('aria-expanded')).toBe('true');
	} finally {
		dialog.remove();
	}
});

test('offline hints update a persistent status region without renaming the home link', async () => {
	vi.stubGlobal('matchMedia', () => ({ matches: true }));
	try {
		renderHeader('reader');
		const home = screen.getByRole('link', { name: 'Heritage Kitchen' });
		const status = screen.getByRole('status');
		expect(status.textContent?.trim()).toBe('');
		offline.markConnection(true);
		await tick();
		expect(status.textContent).toContain('Offline-Modus');
		offline.incomplete = true;
		await tick();
		expect(status.textContent).toContain('Nicht alle Rezepte synchronisiert');
		expect(screen.getByRole('status')).toBe(status);
		expect(screen.getByRole('link', { name: 'Heritage Kitchen' })).toBe(home);
		offline.markConnection(false);
		await tick();
		expect(status.textContent?.trim()).toBe('');
	} finally {
		vi.unstubAllGlobals();
	}
});

test('shows the last complete sync online only for its eligible account', async () => {
	vi.stubGlobal('matchMedia', () => ({ matches: true }));
	try {
		renderHeader('reader');
		offline.lastCompleteSync = { userId: 1, syncedAt: '2026-11-15T12:00:00Z' };
		offline.statusUserId = 1;
		await tick();
		const date = screen.getByText('15.11.2026');
		expect(date.parentElement?.textContent).toContain('Offline verfügbar · Stand');
		expect(date.closest('[role="status"], [aria-live]')).toBeNull();
		const user = auth.user!;
		auth.user = { ...user, id: 2 };
		await tick();
		expect(screen.queryByText('15.11.2026')).toBeNull();
		expect(screen.getByText('Wird synchronisiert …')).toBeTruthy();
		auth.user = { ...user, pending_approval: true };
		await tick();
		expect(screen.queryByText('Wird synchronisiert …')).toBeNull();
		auth.user = null;
		await tick();
		expect(screen.queryByText('Wird synchronisiert …')).toBeNull();
	} finally {
		vi.unstubAllGlobals();
	}
});

test('omits offline availability in a normal browser tab', () => {
	renderHeader('reader');
	expect(screen.queryByRole('button', { name: 'App installieren' })).toBeNull();
	expect(screen.queryByText('Nicht alle Rezepte synchronisiert')).toBeNull();
	expect(screen.queryByText('Wird synchronisiert …')).toBeNull();
});

test('shows neutral initial progress and reports a finished sync failure', async () => {
	vi.stubGlobal('matchMedia', () => ({ matches: true }));
	try {
		renderHeader('reader');
		expect(screen.getByText('Wird synchronisiert …')).toBeTruthy();
		offline.syncing = true;
		offline.incomplete = true;
		await tick();
		expect(screen.getByText('Wird synchronisiert …')).toBeTruthy();
		expect(screen.queryByText('Nicht alle Rezepte synchronisiert')).toBeNull();
		offline.syncing = false;
		offline.statusUserId = 1;
		offline.syncError = 'Der Offline-Speicher ist nicht verfügbar.';
		await tick();
		expect(screen.getByText('Der Offline-Speicher ist nicht verfügbar.')).toBeTruthy();
		expect(screen.getByText('Nicht alle Rezepte synchronisiert')).toBeTruthy();
		expect(screen.queryByText('Wird synchronisiert …')).toBeNull();
	} finally {
		vi.unstubAllGlobals();
	}
});
