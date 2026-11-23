import { expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import * as api from '$lib/api';
import { load as loadLayout } from '../../src/routes/+layout';
import Header from '$lib/components/Header.svelte';
import { offline } from '$lib/stores/offline.svelte';
import { auth } from '$lib/stores/auth.svelte';
import { cookbook } from '$lib/stores/settings.svelte';
import { installedApp, offlineImage } from '$lib/offline/installed';

import type { User } from '$lib/types';

const user = { id: 7, is_active: true, pending_approval: false } as User;

it('marks a missing generation as incomplete even without a stored status', async () => {
	const storage = {
		readMeta: vi.fn().mockResolvedValue(null),
		readStatus: vi.fn().mockResolvedValue(null)
	};
	vi.spyOn(offline, 'storage', 'get').mockReturnValue(storage as typeof offline.storage);
	try {
		await offline.loadStatus(user);
		expect(storage.readMeta).toHaveBeenCalledWith(user.id);
		expect(offline.incomplete).toBe(true);
		expect(offline.statusUserId).toBeNull();
	} finally {
		offline.incomplete = false;
	}
});

it('skips incomplete status for anonymous or ineligible accounts', async () => {
	const storage = { readMeta: vi.fn(), readStatus: vi.fn() };
	vi.spyOn(offline, 'storage', 'get').mockReturnValue(storage as typeof offline.storage);
	for (const account of [
		null,
		{ ...user, pending_approval: true },
		{ ...user, is_active: false }
	]) {
		offline.incomplete = true;
		await offline.loadStatus(account);
		expect(offline.incomplete).toBe(false);
	}
	expect(storage.readMeta).not.toHaveBeenCalled();
});

it('reports the saved complete sync date even after an interrupted update', async () => {
	const syncedAt = '2026-11-15T12:00:00Z';
	const storage = {
		readMeta: vi.fn().mockResolvedValue({ generation: 'complete', syncedAt }),
		readStatus: vi.fn().mockResolvedValue({ state: 'failed', at: '2026-11-16T12:00:00Z' })
	};
	vi.spyOn(offline, 'storage', 'get').mockReturnValue(storage as typeof offline.storage);
	try {
		await offline.loadStatus(user);
		expect(offline.lastCompleteSync).toEqual({ userId: user.id, syncedAt });
		expect(offline.statusUserId).toBe(user.id);
		expect(offline.incomplete).toBe(false);
	} finally {
		await offline.loadStatus(null);
	}
	expect(offline.lastCompleteSync).toBeNull();
	expect(offline.statusUserId).toBeNull();
});

it('loads the synchronized cookbook title on an offline deep link', async () => {
	vi.stubGlobal('matchMedia', () => ({ matches: true }));
	const snapshotSettings = { cookbook_name: 'Familienrezepte' };
	const fetch = vi
		.fn()
		.mockResolvedValue(Response.json(snapshotSettings, { headers: { 'X-Offline': '1' } }));
	try {
		const result = await loadLayout({ fetch } as Parameters<typeof loadLayout>[0]);
		expect(result).toEqual({ settings: snapshotSettings });
		expect(fetch.mock.calls[0]).toEqual([
			'/api/settings',
			expect.objectContaining({
				cache: 'no-store',
				headers: expect.objectContaining({ 'X-Offline-Read': '1' })
			})
		]);
	} finally {
		offline.markConnection(false);
		vi.unstubAllGlobals();
	}
});

it('offers offline data only when launched as an installed app', () => {
	vi.stubGlobal('matchMedia', () => ({ matches: false }));
	expect(installedApp()).toBe(false);
	expect(offlineImage('/media/a.jpg')).toBe('/media/a.jpg');
	vi.stubGlobal('matchMedia', (query: string) => ({
		matches: query === '(display-mode: standalone)'
	}));
	expect(installedApp()).toBe(true);
	expect(offlineImage('/media/a.jpg')).toBe('/media/a.jpg?heritagekitchen-offline=1');
	vi.unstubAllGlobals();
});

it('places offline and incomplete status below the current cookbook title', async () => {
	vi.stubGlobal('matchMedia', () => ({ matches: true }));
	const previous = cookbook.settings;
	const previousUser = auth.user;
	auth.user = null;
	cookbook.settings = { ...previous, cookbook_name: 'Familienrezepte' };
	try {
		render(Header);
		const title = screen.getByRole('link', { name: 'Familienrezepte' });
		const liveRegion = screen.getByRole('status');
		const status = within(liveRegion);
		expect(title.nextElementSibling).toBe(liveRegion);
		expect(status.queryByText('Offline-Modus')).toBeNull();
		offline.incomplete = true;
		offline.markConnection(true);
		await tick();
		const offlineLabel = status.getByText('Offline-Modus');
		expect(status.queryByText('Nicht alle Rezepte synchronisiert')).toBeNull();
		auth.user = user;
		await tick();
		expect(offlineLabel.nextElementSibling).toBe(
			status.getByText('Nicht alle Rezepte synchronisiert')
		);
		offline.markConnection(false);
		await tick();
		expect(screen.getByRole('status')).toBe(liveRegion);
		expect(status.queryByText('Offline-Modus')).toBeNull();
	} finally {
		cookbook.settings = previous;
		auth.user = previousUser;
		offline.incomplete = false;
		offline.markConnection(false);
		vi.unstubAllGlobals();
	}
});

it('recovers connectivity and checks the signed-in account before requesting a sync', async () => {
	vi.stubGlobal('matchMedia', () => ({ matches: true }));
	const fetcher = vi
		.fn()
		.mockRejectedValueOnce(new TypeError('VPN disconnected'))
		.mockResolvedValueOnce(Response.json(user));
	vi.stubGlobal('fetch', fetcher);
	const sync = vi.spyOn(offline, 'sync').mockResolvedValue(undefined);
	try {
		await offline.probe(() => user);
		expect(offline.offline).toBe(true);
		expect(sync).not.toHaveBeenCalled();
		await offline.probe(() => user);
		expect(offline.offline).toBe(false);
		expect(fetcher.mock.calls[1][1]).toMatchObject({
			cache: 'no-store',
			headers: { 'X-Offline-Sync': '1' }
		});
		expect(sync).toHaveBeenCalledWith(user);
	} finally {
		offline.markConnection(false);
		vi.unstubAllGlobals();
	}
});

it('does not send or queue recipe, comment, rating or favorite writes offline', async () => {
	const fetcher = vi.fn();
	vi.stubGlobal('fetch', fetcher);
	offline.markConnection(true);
	try {
		for (const write of [
			() => api.deleteRecipe(1),
			() => api.createRecipeComment(1, 'Muskat'),
			() => api.saveRecipeRating(1, 5),
			() => api.addFavorite(1, user.id),
			() => api.setFavoriteOrder(user.id, [1, 2])
		]) {
			await expect(write()).rejects.toMatchObject({ status: 0 });
		}
		offline.markConnection(false);
		expect(fetcher).not.toHaveBeenCalled();
	} finally {
		offline.markConnection(false);
		vi.unstubAllGlobals();
	}
});
