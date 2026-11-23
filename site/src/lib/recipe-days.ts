// Gruppiert die Schritte mehrtägiger Rezepte nach Tagen; eintägige Rezepte bekommen keine Überschrift.
export function stepGroups<T extends { day: number; position: number }>(recipe: {
	preparation_days: number;
	day_titles: string[] | null;
	steps: T[];
}): { day: number; label: string | null; steps: T[] }[] {
	const ordered = [...recipe.steps].sort((a, b) => a.day - b.day || a.position - b.position);
	const groups: { day: number; label: string | null; steps: T[] }[] = [];
	for (const step of ordered) {
		let group = groups.at(-1);
		if (!group || group.day !== step.day) {
			const title = recipe.day_titles?.[step.day - 1];
			group = {
				day: step.day,
				label:
					recipe.preparation_days > 1
						? title
							? `Tag ${step.day} – ${title}`
							: `Tag ${step.day}`
						: null,
				steps: []
			};
			groups.push(group);
		}
		group.steps.push(step);
	}
	return groups;
}
