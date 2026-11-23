import { formatRange } from './format-time.ts';
import type { Recipe, StepTimeKind } from './types.ts';

export interface EffectiveTime {
	from: number;
	to: number | null;
	fromSteps: boolean;
	manual: { from: number; to: number | null } | null;
}

type TimeSource = Pick<
	Recipe,
	'preparation_time' | 'cooking_time' | 'cooking_time_max' | 'rest_time' | 'rest_time_max'
> & { steps: Pick<Recipe['steps'][number], 'duration_minutes' | 'time_kind'>[] };

export const timeLabels: Record<StepTimeKind, string> = {
	preparation: 'Arbeitszeit',
	cooking: 'Koch-/Backzeit',
	rest: 'Ruhezeit'
};

function effective(
	recipe: TimeSource,
	kind: StepTimeKind,
	from: number | null,
	to: number | null
): EffectiveTime | null {
	const manual = from == null ? null : { from, to };
	const minutes = (recipe.steps ?? [])
		.filter((step) => step.time_kind === kind && step.duration_minutes)
		.map((step) => step.duration_minutes as number);
	if (minutes.length) {
		return {
			from: minutes.reduce((sum, value) => sum + value, 0),
			to: null,
			fromSteps: true,
			manual
		};
	}
	return manual && { ...manual, fromSteps: false, manual };
}

// Schrittzeiten ersetzen den manuellen Wert je Zeitart; nur explizite Zeitfelder zählen.
export function effectiveTimes(recipe: TimeSource) {
	const preparation = effective(recipe, 'preparation', recipe.preparation_time, null);
	const cooking = effective(
		recipe,
		'cooking',
		recipe.cooking_time,
		recipe.cooking_time_max ?? null
	);
	const rest = effective(recipe, 'rest', recipe.rest_time, recipe.rest_time_max ?? null);
	const present = [preparation, cooking, rest].filter((time) => time !== null);
	let total: { from: number; to: number | null } | null = null;
	if (present.length) {
		const from = present.reduce((sum, time) => sum + time.from, 0);
		const to = present.reduce((sum, time) => sum + Math.max(time.from, time.to ?? 0), 0);
		total = { from, to: to > from ? to : null };
	}
	return { preparation, cooking, rest, total };
}

// Listenkarten kennen nur die je Zeitart summierten Schrittzeiten.
export function summaryTimes(
	recipe: Omit<TimeSource, 'steps'> & { step_times?: Partial<Record<StepTimeKind, number | null>> }
) {
	const steps = (['preparation', 'cooking', 'rest'] as const)
		.filter((kind) => recipe.step_times?.[kind])
		.map((kind) => ({ duration_minutes: recipe.step_times![kind]!, time_kind: kind }));
	return effectiveTimes({ ...recipe, steps });
}

export function replacedTimeNotices(recipe: TimeSource): string[] {
	const times = effectiveTimes(recipe);
	const notices: string[] = [];
	for (const [kind, time] of [
		['preparation', times.preparation],
		['cooking', times.cooking],
		['rest', times.rest]
	] as const) {
		if (!time?.fromSteps || !time.manual) continue;
		if (time.manual.from === time.from && time.manual.to === null) continue;
		const manual = formatRange(time.manual.from, time.manual.to);
		const end = manual.endsWith('.') ? '' : '.';
		notices.push(
			`${timeLabels[kind]}: Aus den Schritten werden ${formatRange(time.from, null)} angezeigt statt der manuell eingetragenen ${manual}${end} Die ${manual} bleiben gespeichert.`
		);
	}
	return notices;
}
