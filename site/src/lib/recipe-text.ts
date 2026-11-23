import { formatRange } from './format-time.ts';
import { stepGroups } from './recipe-days.ts';
import { effectiveTimes } from './recipe-times.ts';
import type { Recipe, RecipeIngredient } from './types.ts';

export function ingredientAmount(ingredient: RecipeIngredient, factor: number): string {
	if (ingredient.amount !== null) {
		// Approximate amounts such as a pinch are intentionally not scaled.
		const unit = ingredient.unit?.trim().toLocaleLowerCase('de-DE') ?? '';
		const scalable = !['prise', 'prisen', 'messerspitze', 'messerspitzen', 'nach geschmack'].includes(unit);
		const amount = (Number(ingredient.amount) * (scalable ? factor : 1)).toLocaleString('de-DE', {
			maximumFractionDigits: 3
		});
		return `${amount}${ingredient.unit ? ` ${ingredient.unit}` : ''}`;
	}
	return '';
}

export function recipeText(recipe: Recipe, factor: number): string {
	const lines = [`*${recipe.title}*`];
	if (recipe.origin_person) lines.push(`Von ${recipe.origin_person}`);
	if (recipe.history) lines.push('', 'Geschichte zum Rezept:', recipe.history);
	if (recipe.summary) lines.push('', recipe.summary);
	if (recipe.preparation_days > 1) lines.push(`Über ${recipe.preparation_days} Tage`);
	const times = effectiveTimes(recipe);
	if (times.preparation) lines.push(`Arbeitszeit: ${formatRange(times.preparation.from, null)}`);
	if (times.rest) lines.push(`Ruhezeit: ${formatRange(times.rest.from, times.rest.to)}`);
	if (times.cooking)
		lines.push(`Koch-/Backzeit: ${formatRange(times.cooking.from, times.cooking.to)}`);
	if (times.total)
		lines.push(`Summe der erfassten Zeiten: ${formatRange(times.total.from, times.total.to)}`);
	if (recipe.servings) {
		lines.push(
			`Portionen: ${(recipe.servings * factor).toLocaleString('de-DE', { maximumFractionDigits: 2 })}`
		);
	} else if (factor !== 1) {
		lines.push(`Portionen: ${factor.toLocaleString('de-DE', { maximumFractionDigits: 3 })}`);
	}

	if (recipe.important_notes) lines.push('', 'Wichtiger Hinweis:', recipe.important_notes);
	lines.push('', '*Zutaten*');
	const ingredients = [...recipe.ingredients].sort((a, b) => a.position - b.position);
	let groupPosition: number | null = null;
	for (const ingredient of ingredients) {
		if (ingredient.group_position !== groupPosition) {
			groupPosition = ingredient.group_position;
			const group = recipe.ingredient_groups.find((item) => item.position === groupPosition);
			if (group?.name) lines.push(`${group.name}:`);
		}
		const amount = ingredientAmount(ingredient, factor);
		lines.push(
			`- ${amount ? `${amount} ` : ''}${ingredient.name}${ingredient.note ? ` (${ingredient.note})` : ''}`
		);
	}

	lines.push('', '*Zubereitung*');
	let number = 0;
	for (const group of stepGroups({
		...recipe,
		steps: recipe.steps.map((s) => ({ ...s, day: s.day ?? 1 }))
	})) {
		if (group.label) lines.push('', `${group.label}:`);
		for (const step of group.steps) {
			if (step.heading) lines.push('', `${step.heading}:`);
			lines.push(`${++number}. ${step.instruction}`);
			if (step.note) lines.push(`   ${step.note}`);
		}
	}
	if (recipe.notes) lines.push('', 'Notizen:', recipe.notes);
	return lines.join('\n');
}
