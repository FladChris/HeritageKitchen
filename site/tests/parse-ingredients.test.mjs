import assert from 'node:assert/strict';
import test from 'node:test';
import { parseIngredients } from '../src/lib/parse-ingredients.ts';

test('Überschriften, Mengen und Freitext bleiben erhalten', () => {
	assert.deepEqual(parseIngredients('Guss:\n1/2 kg Zucker\n2 Pck. Vanillezucker\nSalz nach Geschmack\n3 unbekannt Mehl'), [
		{ kind: 'heading', name: 'Guss' },
		{ kind: 'ingredient', amount: '0.5', unit: 'kg', name: 'Zucker', note: null },
		{ kind: 'ingredient', amount: '2', unit: 'Päckchen', name: 'Vanillezucker', note: null },
		{ kind: 'ingredient', amount: null, unit: null, name: 'Salz nach Geschmack', note: null },
		{ kind: 'ingredient', amount: '3', unit: null, name: 'unbekannt Mehl', note: null }
	]);
});

 test('Bereiche und Angaben nach Bedarf', () => {
	assert.deepEqual(parseIngredients('3-4 Eier\netwas Salz\nnach Geschmack Pfeffer'), [
		{ kind: 'ingredient', amount: '4', unit: null, name: 'Eier', note: null },
		{ kind: 'ingredient', amount: null, unit: null, name: 'Salz', note: 'etwas' },
		{ kind: 'ingredient', amount: null, unit: null, name: 'Pfeffer', note: 'nach Geschmack' }
	]);
});
