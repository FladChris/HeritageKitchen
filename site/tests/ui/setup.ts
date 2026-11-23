import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/svelte';
afterEach(() => {
	cleanup();
	vi.useRealTimers();
});
// jsdom has no native modal top layer; browser focus trapping and gestures still
// require the documented real-device checks. These stubs exercise our lifecycle.
HTMLDialogElement.prototype.showModal = function () {
	this.open = true;
};
HTMLDialogElement.prototype.close = function () {
	this.open = false;
};
