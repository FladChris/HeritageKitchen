// Zeigt Minuten ab einer Stunde als "1 Std. 15 Min." an.
export function formatMinutes(minutes: number): string {
	if (minutes >= 1440) {
		const days = Math.floor(minutes / 1440);
		const rest = minutes % 1440;
		return `${days} ${days === 1 ? 'Tag' : 'Tage'}${rest ? ` ${formatMinutes(rest)}` : ''}`;
	}
	if (minutes < 60) return `${minutes} Min.`;
	const hours = Math.floor(minutes / 60);
	const rest = minutes % 60;
	return rest === 0 ? `${hours} Std.` : `${hours} Std. ${rest} Min.`;
}

// Zeigt eine Zeitspanne an, z. B. "20–30 Min." oder "12–16 Std.".
export function formatRange(from: number, to: number | null): string {
	if (to === null || to === from) return formatMinutes(from);
	if (from >= 1440 && from % 1440 === 0 && to % 1440 === 0)
		return `${from / 1440}–${to / 1440} Tage`;
	if (to < 60) return `${from}–${to} Min.`;
	if (to < 1440 && from % 60 === 0 && to % 60 === 0) return `${from / 60}–${to / 60} Std.`;
	return `${formatMinutes(from)} bis ${formatMinutes(to)}`;
}
