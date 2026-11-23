import test from 'node:test';
import assert from 'node:assert/strict';
import { formatMinutes, formatRange } from '../src/lib/format-time.ts';

test('unter einer Stunde bleiben Minuten', () => {
	assert.equal(formatMinutes(45), '45 Min.');
});

test('volle Stunden ohne Minuten', () => {
	assert.equal(formatMinutes(60), '1 Std.');
	assert.equal(formatMinutes(120), '2 Std.');
});

test('Stunden und Minuten', () => {
	assert.equal(formatMinutes(75), '1 Std. 15 Min.');
	assert.equal(formatMinutes(1030), '17 Std. 10 Min.');
});

test('Zeitspannen', () => {
	assert.equal(formatRange(20, 30), '20–30 Min.');
	assert.equal(formatRange(720, 960), '12–16 Std.');
	assert.equal(formatRange(735, 975), '12 Std. 15 Min. bis 16 Std. 15 Min.');
	assert.equal(formatRange(30, null), '30 Min.');
	assert.equal(formatRange(30, 30), '30 Min.');
});

test('Tage und gemischte Dauern ab 24 Stunden', () => {
	assert.equal(formatMinutes(1440), '1 Tag');
	assert.equal(formatMinutes(2880), '2 Tage');
	assert.equal(formatMinutes(1800), '1 Tag 6 Std.');
	assert.equal(formatRange(1440, 2880), '1–2 Tage');
	assert.equal(formatRange(1380, 1440), '23 Std. bis 1 Tag');
	assert.equal(formatMinutes(1501), '1 Tag 1 Std. 1 Min.');
});
