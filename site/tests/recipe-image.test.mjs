import assert from 'node:assert/strict';
import test from 'node:test';
import { coverImage } from '../src/lib/recipe-image.ts';

test('Hauptbild ist das Titelbild, sonst das erste Bild', () => {
	const first = { id: 1 };
	const second = { id: 2 };
	assert.equal(coverImage([first, second]), first);
	assert.equal(coverImage([]), undefined);
	const main = { id: 3, is_main: true };
	assert.equal(coverImage([first, second, main]), main);
});
