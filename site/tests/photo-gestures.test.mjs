import test from 'node:test';
import assert from 'node:assert/strict';
import { swipeDirection, zoomScale, wrappedIndex } from '../src/lib/photo-gestures.ts';
test('horizontal swipes navigate, vertical motion and zoomed panning do not', () => {
	assert.equal(swipeDirection(-100, 10, 1), 1);
	assert.equal(swipeDirection(100, 10, 1), -1);
	assert.equal(swipeDirection(10, 100, 1), 0);
	assert.equal(swipeDirection(40, 0, 1), 0);
	assert.equal(swipeDirection(100, 0, 2), 0);
});
test('pinch zoom is clamped and navigation wraps at both ends', () => {
	assert.equal(zoomScale(1, 200, 100), 2);
	assert.equal(zoomScale(2, 20, 100), 1);
	assert.equal(zoomScale(2, 900, 100), 5);
	assert.equal(wrappedIndex(0, -1, 3), 2);
	assert.equal(wrappedIndex(2, 1, 3), 0);
	assert.equal(wrappedIndex(0, 1, 0), 0);
});
