import assert from 'node:assert/strict';
import test from 'node:test';
import { recipeText } from '../src/lib/recipe-text.ts';

const recipe = {
	title: 'Apfelkuchen',
	origin_person: 'Oma',
	servings: 4,
	important_notes: 'Warm servieren.',
	notes: 'Mit Sahne.',
	ingredient_groups: [{ position: 1, name: 'Teig' }],
	ingredients: [
		{
			position: 2,
			group_position: 1,
			amount: null,
			unit: null,
			name: 'Zimt',
			note: 'nach Geschmack'
		},
		{ position: 1, group_position: 1, amount: '0.5', unit: 'kg', name: 'Mehl', note: 'gesiebt' }
	],
	steps: [{ position: 1, instruction: 'Backen', note: null }]
};

test('Rezepttext enthält Gruppen, umgerechnete Mengen und Hinweise', () => {
	assert.equal(
		recipeText(recipe, 2),
		`*Apfelkuchen*
Von Oma
Portionen: 8

Wichtiger Hinweis:
Warm servieren.

*Zutaten*
Teig:
- 1 kg Mehl (gesiebt)
- Zimt (nach Geschmack)

*Zubereitung*
1. Backen

Notizen:
Mit Sahne.`
	);
});

test('Ohne Ausgangsportionszahl gilt eine Portion', () => {
	assert.match(recipeText({ ...recipe, servings: null }, 1.5), /Portionen: 1,5/);
});

test('Umrechnung zeigt höchstens drei Dezimalstellen und lässt unbestimmte Mengen unverändert', () => {
	const sample = {
		...recipe,
		ingredients: [
			{ position: 0, group_position: null, amount: '1', unit: 'g', name: 'Salz', note: null },
			{ position: 1, group_position: null, amount: null, unit: null, name: 'Zimt', note: 'nach Geschmack' },
			{ position: 2, group_position: null, amount: '1', unit: 'Prise', name: 'Pfeffer', note: null }
		]
	};
	const text = recipeText(sample, 1 / 3);
	assert.match(text, /0,333 g Salz/);
	assert.match(text, /Zimt \(nach Geschmack\)/);
	assert.match(text, /1 Prise Pfeffer/);
	assert.doesNotMatch(text, /0,333333/);
});

test('Geschichte, Tagesüberschriften, Zeiten und Warnung stehen im geteilten Text', () => {
	const text = recipeText(
		{
			...recipe,
			history: 'Von früher.\nJeden Sonntag.',
			summary: 'Ein Familienrezept.',
			preparation_days: 2,
			preparation_time: 20,
			rest_time: 1440,
			rest_time_max: 2880,
			steps: [
				{ position: 0, heading: 'Tag 1 – am Vorabend', instruction: 'Mischen' },
				{ position: 1, heading: 'Tag 2', instruction: 'Backen' }
			]
		},
		1
	);
	assert.ok(text.includes('Geschichte zum Rezept:\nVon früher.\nJeden Sonntag.'));
	assert.ok(text.includes('Über 2 Tage'));
	assert.ok(text.includes('Ruhezeit: 1–2 Tage'));
	assert.ok(text.indexOf('Wichtiger Hinweis:') < text.indexOf('*Zutaten*'));
	assert.ok(text.includes('Tag 1 – am Vorabend:\n1. Mischen'));
	assert.ok(text.includes('Tag 2:\n2. Backen'));
});

test('Rezepttext nennt Schrittzeiten statt manueller Zeit und die Summe der erfassten Zeiten', () => {
	const text = recipeText(
		{
			...recipe,
			cooking_time: 45,
			preparation_time: 20,
			steps: [
				{ position: 0, instruction: 'Backen', duration_minutes: 20, time_kind: 'cooking' },
				{ position: 1, instruction: 'Glasur', duration_minutes: 15, time_kind: 'cooking' }
			]
		},
		1
	);
	assert.ok(text.includes('Koch-/Backzeit: 35 Min.'));
	assert.ok(!text.includes('45 Min.'));
	assert.ok(text.includes('Summe der erfassten Zeiten: 55 Min.'));
});
