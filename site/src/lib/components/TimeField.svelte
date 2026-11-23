<script lang="ts">
	// Zeitfeld in Minuten (wie in der Datenbank), eingegeben wird wahlweise in Minuten oder Stunden.
	// Mit range gibt es zusätzlich ein "bis"-Feld.
	let {
		id,
		label,
		from = $bindable(),
		to = $bindable(null),
		range = false
	}: {
		id: string;
		label: string;
		from: number | null;
		to?: number | null;
		range?: boolean;
	} = $props();

	const divisible = (value: number | null, divisor: number) =>
		value === null || value % divisor === 0;
	let unit = $state(
		Boolean(from || to) && divisible(from, 1440) && divisible(to ?? null, 1440)
			? 1440
			: Boolean(from || to) && divisible(from, 60) && divisible(to ?? null, 60)
				? 60
				: 1
	);
	const factor = $derived(unit);
	const show = (value: number | null) => (value === null ? '' : String(value / factor));
	const read = (text: string) => (text ? Math.round(Number(text) * factor) : null);
</script>

<div class="field">
	<label for={id}>{label}</label>
	<div class="time-field">
		<input
			{id}
			type="number"
			min="0"
			step="any"
			placeholder={range ? 'von' : ''}
			value={show(from)}
			oninput={(e) => (from = read(e.currentTarget.value))}
		/>
		{#if range}
			<input
				type="number"
				min="0"
				step="any"
				placeholder="bis"
				aria-label="{label} bis"
				value={show(to)}
				oninput={(e) => (to = read(e.currentTarget.value))}
			/>
		{/if}
		<select
			aria-label="{label} Einheit"
			value={unit}
			onchange={(e) => (unit = Number(e.currentTarget.value))}
		>
			<option value="1">Minuten</option>
			<option value="60">Stunden</option>
			<option value="1440">Tage</option>
		</select>
	</div>
</div>

<style>
	.time-field {
		display: flex;
		gap: 0.4rem;
	}

	.time-field input {
		min-width: 0;
		flex: 1;
	}

	.time-field select {
		width: auto;
	}
</style>
