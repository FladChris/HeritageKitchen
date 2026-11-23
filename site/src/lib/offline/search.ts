// Mirrors the server's full-text rules (recipe_service._fold_term): case, umlauts and
// accents are folded, "ß" becomes "ss", "ae"/"oe"/"ue" fold like the umlaut, and the term may
// match any recipe text or comment.
import type { Recipe, RecipeComment } from '$lib/types';

// Generated from _build_fold_table in app/services/recipe_service.py.
const FOLD_GROUPS = {
	a: 'ÀÁÂÃÄÅàáâãäåĀāĂăĄą',
	c: 'ÇçĆćĈĉĊċČč',
	d: 'Ďď',
	e: 'ÈÉÊËèéêëĒēĔĕĖėĘęĚě',
	g: 'ĜĝĞğĠġĢģ',
	h: 'Ĥĥ',
	i: 'ÌÍÎÏìíîïĨĩĪīĬĭĮįİ',
	j: 'Ĵĵ',
	k: 'Ķķ',
	l: 'ĹĺĻļĽľ',
	n: 'ÑñŃńŅņŇň',
	o: 'ÒÓÔÕÖòóôõöŌōŎŏŐő',
	r: 'ŔŕŖŗŘř',
	s: 'ŚśŜŝŞşŠš',
	ss: 'ßẞ',
	t: 'ŢţŤť',
	u: 'ÙÚÛÜùúûüŨũŪūŬŭŮůŰűŲų',
	w: 'Ŵŵ',
	y: 'ÝýÿŶŷŸ',
	z: 'ŹźŻżŽž'
};
const FOLD_TABLE = new Map(
	Object.entries(FOLD_GROUPS).flatMap(([replacement, chars]) =>
		[...chars].map((char) => [char, replacement] as const)
	)
);

export function foldText(text: string): string {
	return [...text]
		.map((char) => FOLD_TABLE.get(char) ?? char)
		.join('')
		.toLowerCase()
		.replaceAll('ae', 'a')
		.replaceAll('oe', 'o')
		.replaceAll('ue', 'u');
}

const contains = (value: string | null | undefined, term: string) =>
	value != null && foldText(value).includes(term);

// 0 = title, 1 = ingredient, 2 = other text or comment, null = no match.
export function searchRelevance(
	recipe: Recipe,
	comments: RecipeComment[],
	search: string
): 0 | 1 | 2 | null {
	const term = foldText(search.trim());
	if (contains(recipe.title, term)) return 0;
	if (
		recipe.ingredients.some((item) => contains(item.name, term) || contains(item.note, term)) ||
		recipe.ingredient_groups.some((group) => contains(group.name, term))
	)
		return 1;
	const texts = [
		recipe.summary,
		recipe.origin_person,
		recipe.history,
		recipe.notes,
		recipe.important_notes,
		...recipe.steps.flatMap((step) => [step.instruction, step.heading, step.note]),
		...(recipe.day_titles ?? []),
		...comments.map((comment) => comment.text)
	];
	return texts.some((text) => contains(text, term)) ? 2 : null;
}
