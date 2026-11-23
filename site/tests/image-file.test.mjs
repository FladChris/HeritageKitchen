import assert from 'node:assert/strict';
import test from 'node:test';
import { loadImageFile } from '../src/lib/image-file.ts';

test('existing image downloads preserve their bytes and MIME type for cropping', async (t) => {
	const bytes = new Uint8Array([137, 80, 78, 71]);
	const fetchImage = t.mock.method(globalThis, 'fetch', async () => new Response(bytes, {
		headers: { 'Content-Type': 'image/png' }
	}));
	const file = await loadImageFile('/media/photo.png', 'existing-image.jpg');
	assert.equal(fetchImage.mock.calls[0].arguments[0], '/media/photo.png');
	assert.equal(file.name, 'existing-image.jpg');
	assert.equal(file.type, 'image/png');
	assert.deepEqual(new Uint8Array(await file.arrayBuffer()), bytes);
});

test('a failed HTTP response is never passed to the image cropper as a file', async (t) => {
	const blob = t.mock.fn();
	t.mock.method(globalThis, 'fetch', async () => ({ ok: false, blob }));
	await assert.rejects(loadImageFile('/missing.jpg', 'image.jpg'));
	assert.equal(blob.mock.callCount(), 0);
});

test('a failed image connection reaches the caller error handler', async (t) => {
	const failure = new TypeError('Network unavailable');
	t.mock.method(globalThis, 'fetch', async () => { throw failure; });
	await assert.rejects(loadImageFile('/media/photo.jpg', 'image.jpg'), (error) => error === failure);
});
