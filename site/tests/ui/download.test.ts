import { expect, test, vi } from 'vitest';
import { downloadBlob } from '$lib/download';

test.each([
	[undefined, 60_000],
	[10_000, 10_000]
])('downloads a named file and releases its URL after %s ms', (delay, expectedDelay) => {
	vi.useFakeTimers();
	const blob = new Blob(['document'], { type: 'application/pdf' });
	const createUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:download');
	const revokeUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
	let anchor!: HTMLAnchorElement;
	vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
		anchor = this;
		expect(this.isConnected).toBe(true);
	});
	downloadBlob(blob, 'Öl & Kuchen.pdf', delay);
	expect(createUrl).toHaveBeenCalledExactlyOnceWith(blob);
	expect(anchor.href).toBe('blob:download');
	expect(anchor.download).toBe('Öl & Kuchen.pdf');
	expect(anchor.isConnected).toBe(false);
	vi.advanceTimersByTime(expectedDelay - 1);
	expect(revokeUrl).not.toHaveBeenCalled();
	vi.advanceTimersByTime(1);
	expect(revokeUrl).toHaveBeenCalledExactlyOnceWith('blob:download');
});

test('a failed download still removes its temporary link and releases the object URL', () => {
	vi.useFakeTimers();
	vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:failed-download');
	const revokeUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
	const failure = new Error('Download unavailable');
	vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => { throw failure; });
	expect(() => downloadBlob(new Blob(['document']), 'recipe.pdf')).toThrow(failure);
	expect(document.querySelector('a[download]')).toBeNull();
	vi.advanceTimersByTime(60_000);
	expect(revokeUrl).toHaveBeenCalledExactlyOnceWith('blob:failed-download');
});
