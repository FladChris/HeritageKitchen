import assert from 'node:assert/strict';
import test from 'node:test';
import { stepGroups } from '../src/lib/recipe-days.ts';
import { effectiveTimes, summaryTimes } from '../src/lib/recipe-times.ts';
import { recipeText } from '../src/lib/recipe-text.ts';

const step = (position, day, instruction = `Schritt ${position}`) => ({
	position,
	day,
	instruction,
	note: null
});

test('Schritte werden nach Tagen gruppiert, benannte Tage mit Titel, andere nur mit Nummer', () => {
	const groups = stepGroups({
		preparation_days: 3,
		day_titles: ['Einlegen', ''],
		steps: [step(0, 2), step(1, 1), step(2, 2)]
	});
	assert.deepEqual(
		groups.map((group) => [group.label, group.steps.map((s) => s.position)]),
		[
			['Tag 1 – Einlegen', [1]],
			['Tag 2', [0, 2]]
		]
	);
});

test('eintägige Rezepte haben keine Tagesüberschrift', () => {
	const groups = stepGroups({
		preparation_days: 1,
		day_titles: ['Ignoriert'],
		steps: [step(0, 1), step(1, 1)]
	});
	assert.deepEqual(
		groups.map((group) => [group.label, group.steps.length]),
		[[null, 2]]
	);
	assert.deepEqual(stepGroups({ preparation_days: 1, day_titles: null, steps: [] }), []);
});

test('Rezepttext enthält Tagesabschnitte, aber keine bei einem Tag', () => {
	const recipe = {
		title: 'Brot',
		servings: null,
		ingredients: [],
		ingredient_groups: [],
		preparation_days: 2,
		day_titles: ['Vorteig'],
		steps: [step(0, 2, 'Backen'), step(1, 1, 'Ansetzen')]
	};
	const text = recipeText(recipe, 1);
	assert.ok(text.includes('Tag 1 – Vorteig:\n1. Ansetzen\n\nTag 2:\n2. Backen'));
	assert.ok(!recipeText({ ...recipe, preparation_days: 1 }, 1).includes('Tag 1'));
});

test('Kartenzeiten nutzen summierte Schrittzeiten mit manuellem Rückfall', () => {
	const card = {
		preparation_time: 20,
		cooking_time: 45,
		cooking_time_max: null,
		rest_time: null,
		rest_time_max: null,
		step_times: { preparation: null, cooking: 35, rest: 30 }
	};
	assert.deepEqual(summaryTimes(card).total, { from: 85, to: null });
	assert.equal(summaryTimes({ ...card, step_times: undefined }).total.from, 65);
	assert.equal(effectiveTimes({ ...card, steps: [] }).total.from, 65);
});
