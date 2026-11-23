import { expect, test, vi } from 'vitest';
import { createRawSnippet } from 'svelte';
import { render, screen, fireEvent } from '@testing-library/svelte';
import Modal from '../../src/lib/components/Modal.svelte';

const children = createRawSnippet(() => ({ render: () => '<button>Abbrechen</button>' }));

test('modal opens as a labelled native dialog and closes on Escape or a press on the backdrop', async () => {
	const onclose = vi.fn();
	render(Modal, { title: 'Kategorie löschen?', onclose, children });
	const dialog = screen.getByRole('dialog', { name: 'Kategorie löschen?' }) as HTMLDialogElement;
	expect(dialog.open).toBe(true);
	await fireEvent(dialog, new Event('cancel', { cancelable: true }));
	expect(onclose).toHaveBeenCalledTimes(1);
	await fireEvent.click(screen.getByRole('button', { name: 'Abbrechen' }));
	expect(onclose).toHaveBeenCalledTimes(1);
	await fireEvent.click(dialog);
	expect(onclose).toHaveBeenCalledTimes(1);
	await fireEvent.pointerDown(dialog);
	await fireEvent.click(dialog);
	expect(onclose).toHaveBeenCalledTimes(2);
});

test('modal returns focus to the opener when it closes', () => {
	const opener = document.createElement('button');
	document.body.append(opener);
	opener.focus();
	const { unmount } = render(Modal, { title: 'Bild entfernen?', onclose: () => {}, children });
	unmount();
	expect(document.activeElement).toBe(opener);
	opener.remove();
});
