import { render, screen, waitFor } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';
import { expect, test, vi } from 'vitest';
import Layout from '../../src/routes/+layout.svelte';
import { OFFLINE_WIPE_MESSAGE } from '$lib/offline/wipe-channel';

vi.mock('$lib/stores/auth.svelte', () => ({
	auth: { init: vi.fn(), hasRole: () => false }
}));

test('a wipe-triggered reload shows one status notice without taking focus', async () => {
	sessionStorage.setItem(OFFLINE_WIPE_MESSAGE, '1');
	const props = { data: {}, children: createRawSnippet(() => ({ render: () => '<p>Rezepte</p>' })) };
	const { unmount } = render(Layout, props);
	const notice = await screen.findByText('Die Offline-Daten wurden entfernt. Die App wurde neu geladen.');
	expect(notice.closest('[role="status"]')).toBeTruthy();
	expect(document.activeElement).toBe(document.body);
	expect(sessionStorage.getItem(OFFLINE_WIPE_MESSAGE)).toBeNull();

	unmount();
	render(Layout, props);
	await waitFor(() => expect(screen.queryByText('Die Offline-Daten wurden entfernt. Die App wurde neu geladen.')).toBeNull());
});
