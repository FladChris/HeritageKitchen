import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const css = readFileSync(join(root, 'src/app.css'), 'utf8');
const color = (name) => css.match(new RegExp(`--color-${name}: (#[0-9A-F]{6})`, 'i'))[1];
const luminance = (hex) =>
	hex
		.slice(1)
		.match(/../g)
		.map((v) => parseInt(v, 16) / 255)
		.map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
		.reduce((total, v, i) => total + v * [0.2126, 0.7152, 0.0722][i], 0);
function contrast(a, b) {
	const x = luminance(color(a)),
		y = luminance(color(b));
	return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}
test('paper palette keeps text AA contrast and input/focus borders above 3:1', () => {
	assert.equal(color('bg').toUpperCase(), '#F5F0E6');
	for (const text of ['text', 'text-secondary', 'text-muted', 'primary', 'danger'])
		for (const background of ['bg', 'surface', 'surface-raised'])
			assert.ok(contrast(text, background) >= 4.5, `${text} on ${background}`);
	assert.ok(contrast('primary-contrast', 'primary') >= 4.5);
	assert.ok(contrast('danger-contrast', 'danger') >= 4.5);
	for (const border of ['border-input', 'focus'])
		assert.ok(contrast(border, 'surface-raised') >= 3);
});
test('source contains no old palette, decorative gradients or hosted fonts', () => {
	const files = (dir) =>
		readdirSync(dir, { withFileTypes: true }).flatMap((item) =>
			item.isDirectory() ? files(join(dir, item.name)) : [join(dir, item.name)]
		);
	for (const file of files(join(root, 'src'))) {
		const text = readFileSync(file, 'utf8');
		assert.doesNotMatch(
			text,
			/fonts\.(googleapis|gstatic)\.com|linear-gradient|radial-gradient|gradient-text|--shadow-card|--shadow-raised|--blur-glass|#(?:41352b|51402e|806d59|8b6945|f8f0e4|d9cbb9|d6aa72|e8c99a|302820|afc8a0|f87171|fbbf24)\b/i,
			file
		);
		if (file.endsWith('.svelte'))
			assert.doesNotMatch(text, /#[a-f0-9]{3,8}\b|[★☆✎🗑▦☰✕📷📸🍲🍽↺↻]/iu, file);
	}
});
