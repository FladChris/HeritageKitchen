<script lang="ts">
	import { tick } from 'svelte';
	import type { IngredientInput, RecipeInput } from '$lib/types';
	import { parseIngredients } from '$lib/parse-ingredients';
	import Icon from './Icon.svelte';
	import Modal from './Modal.svelte';

	let { ingredients = $bindable(), groups = $bindable() }: {
		ingredients: IngredientInput[];
		groups: RecipeInput['ingredient_groups'];
	} = $props();

	let pendingRemoval = $state<{ index: number } | null>(null);
	let openNotes = $state(new Set<number>());
	type Row =
		| { id: number; kind: 'heading'; name: string }
		| { id: number; kind: 'ingredient'; value: IngredientInput };
	let nextId = 0;
	function initialRows(): Row[] {
		const rows: Row[] = [];
		const orderedGroups = [...groups].sort((a, b) => a.position - b.position);
		const orderedIngredients = [...ingredients].sort((a, b) => a.position - b.position);
		for (const ingredient of orderedIngredients.filter((item) => item.group_position === null))
			rows.push({ id: nextId++, kind: 'ingredient', value: ingredient });
		for (const group of orderedGroups) {
			rows.push({ id: nextId++, kind: 'heading', name: group.name });
			for (const ingredient of orderedIngredients.filter((item) => item.group_position === group.position))
				rows.push({ id: nextId++, kind: 'ingredient', value: ingredient });
		}
		return rows;
	}
	let rows = $state<Row[]>(initialRows());
	let bulkText = $state('');
	let showBulk = $state(false);
	let preview = $state(false);
	const parsed = $derived(parseIngredients(bulkText));

	$effect(() => {
		const nextGroups: RecipeInput['ingredient_groups'] = [];
		const nextIngredients: IngredientInput[] = [];
		let groupPosition: number | null = null;
		for (const row of rows) {
			if (row.kind === 'heading') {
				groupPosition = nextGroups.length;
				nextGroups.push({ position: groupPosition, name: row.name });
			} else {
				nextIngredients.push({
					...row.value,
					position: nextIngredients.length,
					group_position: groupPosition
				});
			}
		}
		groups = nextGroups;
		ingredients = nextIngredients;
	});

	function showNote(index: number) {
		openNotes = new Set(openNotes).add(index);
	}

	function formatAmount(index: number) {
		const row = rows[index];
		if (row.kind !== 'ingredient') return;
		const amount = row.value.amount;
		if (amount && /^\d+(?:[,.]\d+)?$/.test(amount)) {
			row.value.amount = String(Number(amount.replace(',', '.'))).replace('.', ',');
		}
	}

	function validateAmount(input: HTMLInputElement) {
		const value = input.value.trim();
		const valid =
			!value ||
			(/^\d+(?:[,.]\d+|\/\d+)?$/.test(value) &&
				(!value.includes('/') || Number(value.split('/')[1]) !== 0));
		input.setCustomValidity(valid ? '' : 'Bitte eine Zahl eingeben (z. B. 1,5 oder 1/2).');
	}

	function newIngredient(): Row {
		return {
			id: nextId++,
			kind: 'ingredient',
			value: { position: 0, group_position: null, name: '', amount: null, unit: null, note: null }
		};
	}

	function addIngredient() {
		rows.push(newIngredient());
	}

	async function addIngredientAfter(index: number) {
		const row = newIngredient();
		rows.splice(index + 1, 0, row);
		await tick();
		document.querySelector<HTMLInputElement>(`[data-ingredient-name="${row.id}"]`)?.focus();
	}

	function addGroup() {
		rows.push({ id: nextId++, kind: 'heading', name: '' });
	}

	function removeGroup(index: number) {
		rows.splice(index, 1);
	}

	function moveRow(index: number, direction: -1 | 1) {
		const target = index + direction;
		if (target < 0 || target >= rows.length) return;
		[rows[index], rows[target]] = [rows[target], rows[index]];
	}

	function ingredientHasContent(ingredient: (typeof ingredients)[number]) {
		return Boolean(ingredient.name || ingredient.amount || ingredient.unit || ingredient.note);
	}

	function removeIngredient(index: number) {
		const row = rows[index];
		if (row.kind === 'ingredient' && ingredientHasContent(row.value)) {
			pendingRemoval = { index };
			return;
		}
		doRemoveIngredient(index);
	}

	function doRemoveIngredient(index: number) {
		const id = rows[index].id;
		rows.splice(index, 1);
		openNotes.delete(id);
	}

	function acceptBulk() {
		for (const line of parsed) {
			if (line.kind === 'heading') rows.push({ id: nextId++, kind: 'heading', name: line.name });
			else {
				const row = newIngredient();
				if (row.kind === 'ingredient')
					Object.assign(row.value, {
						amount: line.amount,
						unit: line.unit,
						name: line.name,
						note: line.note
					});
				rows.push(row);
			}
		}
		bulkText = '';
		preview = false;
		showBulk = false;
	}

	function confirmRemoval() {
		if (!pendingRemoval) return;
		doRemoveIngredient(pendingRemoval.index);
		pendingRemoval = null;
	}

	function cancelRemoval() {
		pendingRemoval = null;
	}
</script>

<section class="card form-section">
	<div class="section-header">
		<h2>Zutaten</h2>
		<div class="ingredient-add-buttons">
			<button type="button" class="btn btn-secondary btn-sm" onclick={addIngredient}
				><Icon name="plus" /> Zutat</button
			>
			<button type="button" class="btn btn-secondary btn-sm" onclick={addGroup}
				><Icon name="plus" /> Überschrift</button
			>
		</div>
	</div>
	{#if showBulk}
		<div class="field bulk-input">
			<label for="bulk-ingredients">Mehrere Zutaten einfügen</label>
			<textarea
				id="bulk-ingredients"
				rows="6"
				bind:value={bulkText}
				oninput={() => (preview = false)}
				placeholder="Guss:&#10;200 g Zucker"></textarea>
			{#if preview}
				<div class="bulk-preview">
					{#each parsed as line}
						<div>
							{line.kind === 'heading'
								? `Überschrift: ${line.name}`
								: `${line.amount ?? '–'} | ${line.unit ?? '–'} | ${line.name}`}
						</div>
					{/each}
				</div>
			{/if}
			<div class="ingredient-add-buttons">
				{#if preview}<button
						type="button"
						class="btn btn-primary btn-sm"
						onclick={acceptBulk}
						disabled={parsed.length === 0}>Übernehmen</button
					>
				{:else}<button
						type="button"
						class="btn btn-secondary btn-sm"
						onclick={() => (preview = true)}
						disabled={parsed.length === 0}>Vorschau</button
					>{/if}
				<button
					type="button"
					class="btn btn-secondary btn-sm"
					onclick={() => {
						showBulk = false;
						preview = false;
						bulkText = '';
					}}>Abbrechen</button
				>
			</div>
		</div>
	{:else}
		<button type="button" class="more-details-toggle" onclick={() => (showBulk = true)}
			>Mehrere Zutaten einfügen</button
		>
	{/if}
	{#if rows.length === 0}
		<p class="muted">Noch keine Zutaten hinzugefügt.</p>
	{/if}
	{#each rows as row, index (row.id)}
		{#if row.kind === 'heading'}
			<div class="list-row group-row">
				<div class="group-fields">
					<input
						type="text"
						aria-label="Überschrift"
						placeholder="Überschrift *"
						maxlength="150"
						required
						bind:value={row.name}
					/>
					<button type="button" class="link-button" onclick={() => addIngredientAfter(index)}
						><Icon name="plus" /> Zutat darunter</button
					>
				</div>
				<div class="list-row-actions">
					<button
						type="button"
						class="icon-btn"
						aria-label="Überschrift nach oben verschieben"
						title="Überschrift nach oben verschieben"
						onclick={() => moveRow(index, -1)}
						disabled={index === 0}><Icon name="up" /></button
					>
					<button
						type="button"
						class="icon-btn"
						aria-label="Überschrift nach unten verschieben"
						title="Überschrift nach unten verschieben"
						onclick={() => moveRow(index, 1)}
						disabled={index === rows.length - 1}><Icon name="down" /></button
					>
					<button
						type="button"
						class="icon-btn danger"
						aria-label="Überschrift entfernen"
						title="Überschrift entfernen"
						onclick={() => removeGroup(index)}><Icon name="close" /></button
					>
				</div>
			</div>
		{:else}
			<div class="list-row ingredient-row">
				<div class="list-row-fields ingredient-fields">
					<input
						type="text"
						aria-label="Menge"
						placeholder="Menge"
						bind:value={row.value.amount}
						oninput={(event) => validateAmount(event.currentTarget)}
						onblur={() => formatAmount(index)}
						class="ingredient-amount"
					/>
					<input
						type="text"
						aria-label="Einheit"
						placeholder="Einheit"
						list="ingredient-units"
						bind:value={row.value.unit}
						class="ingredient-unit"
					/>
					<input
						type="text"
						aria-label="Zutat"
						placeholder="Zutat *"
						required
						bind:value={row.value.name}
						class="ingredient-name"
						data-ingredient-name={row.id}
						onkeydown={(event) => {
							if (event.key === 'Enter' && !event.isComposing) {
								event.preventDefault();
								addIngredientAfter(index);
							}
						}}
					/>
					<div class="ingredient-options">
						{#if !row.value.note && !openNotes.has(row.id)}<button
								type="button"
								class="link-button"
								onclick={() => showNote(row.id)}><Icon name="plus" /> Notiz</button
							>{/if}
					</div>
					{#if row.value.note || openNotes.has(row.id)}<input
							type="text"
							aria-label="Notiz zur Zutat"
							placeholder="Notiz"
							bind:value={row.value.note}
							class="ingredient-extra"
						/>{/if}
				</div>
				<div class="list-row-actions">
					<button
						type="button"
						class="icon-btn"
						aria-label="Zutat nach oben verschieben"
						title="Zutat nach oben verschieben"
						onclick={() => moveRow(index, -1)}
						disabled={index === 0}><Icon name="up" /></button
					>
					<button
						type="button"
						class="icon-btn"
						aria-label="Zutat nach unten verschieben"
						title="Zutat nach unten verschieben"
						onclick={() => moveRow(index, 1)}
						disabled={index === rows.length - 1}><Icon name="down" /></button
					>
					<button
						type="button"
						class="icon-btn danger"
						aria-label="Zutat entfernen"
						title="Zutat entfernen"
						onclick={() => removeIngredient(index)}><Icon name="close" /></button
					>
				</div>
			</div>
		{/if}
	{/each}
	<datalist id="ingredient-units">
		{#each ['g', 'kg', 'ml', 'l', 'EL', 'TL', 'Prise', 'Stück', 'Päckchen'] as unit}
			<option value={unit}></option>
		{/each}
	</datalist>
</section>

{#if pendingRemoval}
	<Modal
		title="Zutat entfernen?"
		onclose={cancelRemoval}
	>
		<p class="muted">Die eingegebenen Angaben gehen dabei verloren.</p>
		<div class="modal-actions">
			<button type="button" class="btn btn-secondary" onclick={cancelRemoval}>Abbrechen</button>
			<button type="button" class="btn btn-danger" onclick={confirmRemoval}>Entfernen</button>
		</div>
	</Modal>
{/if}

<style>
	.form-section {
		padding: 1.5rem;
		margin-bottom: 1.5rem;
	}

	.section-header {
		flex-wrap: wrap;
		gap: 0.5rem;
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
	}

	.section-header h2 {
		margin: 0;
	}

	.more-details-toggle {
		background: none;
		border: 1px dashed var(--color-border);
		border-radius: var(--radius-sm);
		color: var(--color-text-muted);
		padding: 0.6em 0.9em;
		min-height: 44px;
		font-size: var(--text-sm);
		font-weight: 600;
		text-align: left;
		width: 100%;
	}

	.more-details-toggle:hover {
		color: var(--color-text);
		border-color: var(--color-border-strong);
	}

	.list-row {
		display: flex;
		gap: 0.75rem;
		align-items: start;
		padding: 0.75rem 0;
		border-bottom: 1px dashed var(--color-border);
	}

	.list-row:last-child {
		border-bottom: none;
	}

	.list-row-fields {
		min-width: 0;
		flex: 1;
		display: grid;
		gap: 0.5rem;
	}

	.ingredient-fields {
		grid-template-columns: 90px 90px minmax(150px, 1fr);
		min-width: 0;
	}

	.ingredient-options,
	.ingredient-extra {
		grid-column: 1 / -1;
	}
	.ingredient-options {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 1rem;
	}
	.ingredient-add-buttons {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.group-fields {
		flex: 1;
		min-width: 0;
		display: grid;
		gap: 0.4rem;
	}
	.group-fields input {
		width: 100%;
		min-width: 0;
		background: var(--color-surface-raised);
		border: 1px solid var(--color-border-input);
		border-radius: var(--radius-sm);
		padding: 0.5em 0.65em;
	}
	.bulk-input {
		margin-bottom: 1rem;
	}
	.bulk-preview {
		padding: 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
	}

	.ingredient-fields input {
		background: var(--color-surface-raised);
		border: 1px solid var(--color-border-input);
		border-radius: var(--radius-sm);
		padding: 0.5em 0.65em;
		width: 100%;
	}

	.list-row-actions {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		flex-shrink: 0;
		flex-wrap: wrap;
		max-width: 100%;
	}

	@media (min-width: 641px) {
		.ingredient-row .list-row-actions,
		.group-row .list-row-actions {
			flex-direction: row;
		}
	}

	@media (max-width: 640px) {
		.ingredient-fields {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}

		.ingredient-name {
			grid-column: 1 / -1;
			grid-row: 1;
		}

		/* Fields get the full width; the row actions sit on their own line. */
		.list-row {
			flex-wrap: wrap;
		}

		.list-row-fields,
		.group-fields {
			flex-basis: 100%;
		}

		.list-row-actions {
			flex-direction: row;
			margin-left: auto;
		}

		/* Ingredient actions share the line of the "Notiz" / "Zutat darunter" link. */
		.ingredient-options {
			order: 1;
			min-height: 44px;
		}

	}
</style>
