export type ParsedLine = { kind: 'heading'; name: string } | { kind: 'ingredient'; amount: string | null; unit: string | null; name: string; note: string | null };

const units: Record<string, string> = {
	g: 'g', kg: 'kg', ml: 'ml', l: 'l', el: 'EL', tl: 'TL', prise: 'Prise', stück: 'Stück', päckchen: 'Päckchen', 'pck.': 'Päckchen', pkg: 'Päckchen', blatt: 'Blatt', tropfen: 'Tropfen', bund: 'Bund', dose: 'Dose', becher: 'Becher', glas: 'Glas', tasse: 'Tasse', paket: 'Paket', pakete: 'Pakete'
};

function number(value: string): number {
	if (value.includes('/')) {
		const [top, bottom] = value.split('/').map(Number);
		return top / bottom;
	}
	return Number(value.replace(',', '.'));
}

export function parseIngredients(text: string): ParsedLine[] {
	return text.split(/\r?\n/).map((line): ParsedLine | null => {
		const value = line.trim();
		if (!value) return null;
		const heading = /^(?:Name:\s*)?(.+):$/i.exec(value);
		if (heading) return { kind: 'heading', name: heading[1].trim() };
		const note = /^(etwas|nach Geschmack)\s+(.+)$/i.exec(value);
		if (note) return { kind: 'ingredient', amount: null, unit: null, name: note[2], note: note[1] };
		const amount = /^(\d+(?:[,.]\d+|\/\d+)?)(?:\s*[-–]\s*(\d+(?:[,.]\d+|\/\d+)?))?\s+(.+)$/.exec(value);
		if (!amount) return { kind: 'ingredient', amount: null, unit: null, name: value, note: null };
		const rest = amount[3];
		const unit = /^([^\s]+)\s+(.+)$/.exec(rest);
		const parsed = Math.max(number(amount[1]), amount[2] ? number(amount[2]) : 0);
		const result = Number.isFinite(parsed) ? String(parsed) : null;
		if (!unit || !units[unit[1].toLowerCase()]) return { kind: 'ingredient', amount: result, unit: null, name: rest, note: null };
		return { kind: 'ingredient', amount: result, unit: units[unit[1].toLowerCase()], name: unit[2], note: null };
	}).filter((line): line is ParsedLine => line !== null);
}
