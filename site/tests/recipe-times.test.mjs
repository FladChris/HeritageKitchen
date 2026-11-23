import assert from 'node:assert/strict';
import test from 'node:test';
import { formatMinutes } from '../src/lib/format-time.ts';
import { effectiveTimes, replacedTimeNotices } from '../src/lib/recipe-times.ts';

const base = {
	preparation_time: null,
	cooking_time: null,
	cooking_time_max: null,
	rest_time: null,
	rest_time_max: null,
	steps: []
};
const step = (duration_minutes, time_kind) => ({ duration_minutes, time_kind });

test('Schrittzeiten ersetzen den manuellen Wert je Zeitart und sind danach wieder entfernbar', () => {
	const recipe = {
		...base,
		preparation_time: 30,
		steps: [step(20, 'preparation'), step(5, 'preparation')]
	};
	assert.equal(effectiveTimes(recipe).preparation.from, 25);
	assert.equal(effectiveTimes({ ...recipe, steps: [] }).preparation.from, 30);
});

test('Summe addiert parallele Zeiten ohne Abzug', () => {
	const recipe = {
		...base,
		steps: [step(20, 'preparation'), step(40, 'cooking'), step(10, 'cooking')]
	};
	assert.deepEqual(effectiveTimes(recipe).total, { from: 70, to: null });
});

test('30 Stunden bleiben Minuten und nicht Tage der Zubereitung', () => {
	const recipe = { ...base, preparation_days: 4, steps: [step(1800, 'rest')] };
	assert.deepEqual(effectiveTimes(recipe).total, { from: 1800, to: null });
	assert.equal(formatMinutes(1800), '1 Tag 6 Std.');
	assert.equal(formatMinutes(1500), '1 Tag 1 Std.');
});

test('Freitext wird nicht ausgewertet und fehlende Zeiten werden nicht geschätzt', () => {
	const recipe = { ...base, steps: [{ ...step(null, null), instruction: '30 Minuten köcheln' }] };
	assert.equal(effectiveTimes(recipe).total, null);
	assert.equal(effectiveTimes(recipe).rest, null);
});

test('Bereiche und Null-Werte der manuellen Zeiten', () => {
	const recipe = { ...base, preparation_time: 10, cooking_time: 30, cooking_time_max: 40 };
	assert.deepEqual(effectiveTimes(recipe).total, { from: 40, to: 50 });
	assert.deepEqual(effectiveTimes({ ...base, preparation_time: 0 }).total, { from: 0, to: null });
});

test('Hinweis nennt Zeitart, Anzeigewert und gespeicherten Wert nur bei Abweichung', () => {
	const recipe = { ...base, cooking_time: 45, steps: [step(20, 'cooking'), step(15, 'cooking')] };
	assert.deepEqual(replacedTimeNotices(recipe), [
		'Koch-/Backzeit: Aus den Schritten werden 35 Min. angezeigt statt der manuell eingetragenen 45 Min. Die 45 Min. bleiben gespeichert.'
	]);
	assert.deepEqual(replacedTimeNotices({ ...recipe, cooking_time: 35 }), []);
	assert.deepEqual(replacedTimeNotices({ ...recipe, cooking_time: null }), []);
});
