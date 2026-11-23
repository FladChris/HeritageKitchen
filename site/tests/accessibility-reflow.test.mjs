import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

function styles(path) {
	return readFileSync(new URL('../src/' + path, import.meta.url), 'utf8').split('<style>').at(-1);
}

test('the cropper uses flex only while the native dialog is open', () => {
	const css = styles('lib/components/ImageCropper.svelte');
	assert.doesNotMatch(css, /\.cropper-backdrop\s*\{[^}]*display\s*:/);
	assert.match(css, /\.cropper-backdrop\[open\]\s*\{[^}]*display:\s*flex/);
});

test('critical dialog and gallery controls keep viewport and wrapping guards', () => {
	assert.match(styles('lib/components/Modal.svelte'), /dialog\s*\{[^}]*width:\s*min\(26rem, calc\(100% - 2rem\)\)/);
	assert.match(styles('lib/components/Modal.svelte'), /\(\.modal-actions\)\s*\{[^}]*flex-wrap:\s*wrap/);
	assert.match(styles('lib/components/ImageCropper.svelte'), /\.cropper-dialog\s*\{[^}]*width:\s*min\(900px, 100%\)[^}]*overflow:\s*auto/);
	assert.match(styles('lib/components/PhotoViewer.svelte'), /\.viewer-toolbar\s*\{[^}]*flex-wrap:\s*wrap/);
	const app = styles('app.css');
	assert.match(app, /\.recipe-grid\s*\{[^}]*minmax\(min\(100%, 250px\), 1fr\)/);
	assert.match(app, /\.field-row\s*\{[^}]*minmax\(min\(100%, 140px\), 1fr\)/);
	assert.match(app, /\.settings-page\s+\.settings-actions\s*\{[^}]*flex-wrap:\s*wrap/);
});

test('recipe photo placeholders stay visible on narrow screens', () => {
	const css = styles('lib/components/RecipeCard.svelte');
	assert.match(css, /\.photo-placeholder\s*\{[^}]*display:\s*grid/);
	assert.doesNotMatch(css, /@media[^]*\.(?:no-photo|photo-placeholder)\s*\{[^}]*display:\s*none/);
});
