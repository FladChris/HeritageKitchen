import type { Recipe } from './types';

const fieldNames = [
	'title', 'summary', 'preparation_time', 'cooking_time', 'cooking_time_max',
	'rest_time', 'rest_time_max', 'servings', 'history', 'preparation_days',
	'day_titles', 'origin_person', 'notes', 'important_notes', 'category_id'
] as const;

function openedSnapshot(recipe: Recipe): Record<string, unknown> {
	const snapshot: Record<string, unknown> = {};
	for (const field of fieldNames) snapshot[field] = recipe[field];
	snapshot.category_name = recipe.category?.name ?? null;
	snapshot.ingredient_groups = [...recipe.ingredient_groups]
		.sort((a, b) => a.position - b.position)
		.map(({ position, name }) => ({ position, name }));
	snapshot.ingredients = [...recipe.ingredients]
		.sort((a, b) => a.position - b.position)
		.map(({ position, name, amount, unit, note, group_position }) => ({
			position,
			name,
			amount: amount === null ? null : Number(amount).toFixed(3),
			unit,
			note,
			group_position
		}));
	snapshot.steps = [...recipe.steps]
		.sort((a, b) => a.position - b.position)
		.map(({ position, instruction, heading, is_important, note, duration_minutes, time_kind, day }) => ({
			position,
			instruction,
			heading,
			is_important,
			note,
			...(duration_minutes === null ? {} : { duration_minutes, time_kind }),
			...(day === 1 ? {} : { day })
		}));
	// Recipe.images is returned in gallery order; the response has no position property.
	snapshot.images = recipe.images.map(({ file_path, alt_text, is_main }) => ({
		file_path, alt_text, is_main
	}));
	return snapshot;
}

function stable(value: unknown): unknown {
	if (Array.isArray(value)) return value.map(stable);
	if (value && typeof value === 'object') {
		return Object.fromEntries(
			Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, entry]) => [key, stable(entry)])
		);
	}
	return value;
}

/** Compare against what this editor actually loaded, without accessing admin history. */
export function changedRecipeFields(
	opened: Recipe,
	latest: Record<string, unknown>
): Record<string, { before: unknown; after: unknown }> {
	const before = openedSnapshot(opened);
	const changes: Record<string, { before: unknown; after: unknown }> = {};
	for (const [field, after] of Object.entries(latest)) {
		if (field === 'category_name' && before.category_id === latest.category_id) continue;
		if (JSON.stringify(stable(before[field])) !== JSON.stringify(stable(after))) {
			changes[field] = { before: before[field], after };
		}
	}
	return changes;
}
