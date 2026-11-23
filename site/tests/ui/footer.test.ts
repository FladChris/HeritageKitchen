import { beforeEach, expect, test } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import Footer from '../../src/lib/components/Footer.svelte';
import { cookbook, defaultSettings } from '../../src/lib/stores/settings.svelte';

beforeEach(() => {
	cookbook.settings = { ...defaultSettings };
});

test('uses the cookbook name until an individual footer is set', async () => {
	cookbook.settings = { ...defaultSettings, cookbook_name: 'Familienrezepte' };
	render(Footer);
	expect(screen.getByText('Familienrezepte').closest('footer')).toBeTruthy();

	cookbook.settings = { ...cookbook.settings, footer_text: 'Mit Liebe gesammelt seit 2026' };
	await waitFor(() => expect(screen.getByText('Mit Liebe gesammelt seit 2026')).toBeTruthy());
	expect(screen.queryByText('Familienrezepte')).toBeNull();

	cookbook.settings = { ...cookbook.settings, footer_text: '' };
	await waitFor(() => expect(screen.getByText('Familienrezepte')).toBeTruthy());
});

test('renders user-defined footer text as plain text', () => {
	const content = '<b>Unsere Rezepte</b>';
	cookbook.settings = { ...defaultSettings, footer_text: content };
	const { container } = render(Footer);
	expect(screen.getByText(content)).toBeTruthy();
	expect(container.querySelector('footer b')).toBeNull();
});
