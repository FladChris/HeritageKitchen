<script lang="ts">
	import Modal from './Modal.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import type { Category, RecipeInput } from '$lib/types';
	import { auth } from '$lib/stores/auth.svelte';
	import RecipeIngredientsEditor from './RecipeIngredientsEditor.svelte';
	import TimeField from './TimeField.svelte';

	let {
		form = $bindable(),
		categories
	}: {
		form: RecipeInput;
		categories: Category[] | null;
	} = $props();

	// The extra fields start tucked away every time — editing an existing
	// recipe shouldn't dump a long form on screen just because some optional
	// field happens to be filled in. The toggle label says when there's
	// something inside already, so nothing is lost by surprise.
	let showMoreDetails = $state(false);
	let titleError = $state('');
	let titleInput: HTMLInputElement;
	let categoryError = $state('');

	export function validate() {
		if (daysInput && !validateDays(daysInput)) {
			daysInput.focus();
			return false;
		}
		if (pendingDays !== null) return false;
		if (titleInput.value.trim()) return true;
		showTitleError(titleInput);
		titleInput.focus();
		return false;
	}

	function showTitleError(input: HTMLInputElement) {
		titleError = 'Bitte einen Titel angeben.';
		input.setCustomValidity(titleError);
	}

	const hasMoreDetails = $derived(
		Boolean(
			form.summary ||
			form.preparation_time ||
			form.cooking_time ||
			form.rest_time ||
			form.origin_person ||
			form.history ||
			form.preparation_days > 1 ||
			form.notes ||
			form.important_notes
		)
	);

	const stepHasDetails = (step: (typeof form.steps)[number]) =>
		Boolean(step.is_important || step.note || step.duration_minutes);

	let openStepDetails = $state(new Set<number>());

	let pendingRemoval = $state<{ index: number } | null>(null);
	function toggleStepDetails(index: number) {
		const next = new Set(openStepDetails);
		if (next.has(index)) next.delete(index);
		else next.add(index);
		openStepDetails = next;
	}

	function addStep() {
		form.steps = [
			...form.steps,
			{
				position: form.steps.length,
				instruction: '',
				heading: null,
				is_important: false,
				note: null,
				duration_minutes: null,
				time_kind: null,
				day: 1
			}
		];
	}

	let daysInput = $state<HTMLInputElement>();
	let daysError = $state('');
	let pendingDays = $state<number | null>(null);
	let reassignments = $state<Record<number, number>>({});
	const affectedSteps = $derived(
		pendingDays === null
			? []
			: form.steps.flatMap((step, index) => (step.day > pendingDays! ? [index] : []))
	);
	const dayNumbers = $derived(
		Array.from({ length: Math.min(14, Math.max(1, form.preparation_days || 1)) }, (_, i) => i + 1)
	);

	function applyDays(days: number) {
		form.preparation_days = days;
		if (form.day_titles) form.day_titles = form.day_titles.slice(0, days);
	}

	function validateDays(input: HTMLInputElement) {
		daysError = input.validity.rangeOverflow
			? 'Ein Rezept darf höchstens 14 Zubereitungstage umfassen.'
			: '';
		return !daysError;
	}

	function changeDays(input: HTMLInputElement) {
		if (!validateDays(input)) return;
		const days = Math.max(1, Math.round(Number(input.value)) || 1);
		if (form.steps.some((step) => step.day > days)) {
			pendingDays = days;
			reassignments = {};
			return;
		}
		applyDays(days);
		if (daysInput) daysInput.value = String(days);
	}

	function confirmReassignment() {
		if (pendingDays === null) return;
		for (const [index, day] of Object.entries(reassignments)) form.steps[Number(index)].day = day;
		applyDays(pendingDays);
		pendingDays = null;
	}

	function cancelReassignment() {
		pendingDays = null;
		if (daysInput) daysInput.value = String(form.preparation_days);
	}

	function setDayTitle(day: number, title: string) {
		const titles = [...(form.day_titles ?? [])];
		while (titles.length < day) titles.push('');
		titles[day - 1] = title;
		form.day_titles = titles;
	}

	function setStepDuration(index: number, text: string) {
		const minutes = text ? Math.round(Number(text)) : null;
		const step = form.steps[index];
		step.duration_minutes = minutes;
		step.time_kind = minutes === null ? null : (step.time_kind ?? 'preparation');
	}

	function stepHasContent(step: (typeof form.steps)[number]) {
		return Boolean(step.instruction || stepHasDetails(step));
	}

	function removeStep(index: number) {
		if (stepHasContent(form.steps[index])) {
			pendingRemoval = { index };
			return;
		}
		doRemoveStep(index);
	}

	function doRemoveStep(index: number) {
		form.steps = form.steps
			.filter((_, i) => i !== index)
			.map((step, i) => ({ ...step, position: i }));
		const next = new Set<number>();
		openStepDetails.forEach((i) => {
			if (i < index) next.add(i);
			else if (i > index) next.add(i - 1);
		});
		openStepDetails = next;
	}

	function confirmRemoval() {
		if (!pendingRemoval) return;
		doRemoveStep(pendingRemoval.index);
		pendingRemoval = null;
	}

	function cancelRemoval() {
		pendingRemoval = null;
	}

	function moveStep(index: number, direction: -1 | 1) {
		const target = index + direction;
		if (target < 0 || target >= form.steps.length) return;
		const list = [...form.steps];
		[list[index], list[target]] = [list[target], list[index]];
		form.steps = list.map((step, i) => ({ ...step, position: i }));
	}
</script>

<section class="card form-section">
	<h2>Grunddaten</h2>
	<div class="field">
		<label for="title">Titel *</label>
		<input
			id="title"
			bind:this={titleInput}
			aria-invalid={titleError ? 'true' : undefined}
			aria-describedby={titleError ? 'title-error' : undefined}
			type="text"
			bind:value={form.title}
			required
			maxlength="150"
			oninput={(event) => {
				const valid = Boolean(event.currentTarget.value.trim());
				event.currentTarget.setCustomValidity(valid ? '' : 'Bitte einen Titel angeben.');
				if (titleError) titleError = valid ? '' : 'Bitte einen Titel angeben.';
			}}
			oninvalid={(event) => showTitleError(event.currentTarget)}
		/>
		{#if titleError}<p id="title-error" class="alert alert-error" role="alert">{titleError}</p>{/if}
	</div>

	<div class="field">
		<label for="category">Kategorie *</label>
		<select
			id="category"
			aria-invalid={categoryError ? 'true' : undefined}
			aria-describedby={categoryError ? 'category-error' : undefined}
			required
			value={form.category_id ?? ''}
			oninvalid={(e) => {
				e.currentTarget.setCustomValidity('Bitte wähle eine Kategorie aus.');
				categoryError = 'Bitte wähle eine Kategorie aus.';
			}}
			onchange={(e) => {
				e.currentTarget.setCustomValidity('');
				categoryError = '';
				form.category_id = e.currentTarget.value ? Number(e.currentTarget.value) : null;
			}}
		>
			<option value="" disabled>Bitte wählen</option>
			{#each categories ?? [] as category (category.id)}
				<option value={category.id}>{category.name}</option>
			{/each}
		</select>
		{#if categoryError}<p id="category-error" class="alert alert-error" role="alert">{categoryError}</p>{/if}
		{#if categories?.length === 0}
			{#if auth.hasRole('admin')}
				<p class="muted">
					Es ist noch keine Kategorie vorhanden. Lege auf der <a href="/">Startseite</a> eine an.
				</p>
			{:else}
				<p class="muted">
					Es ist noch keine Kategorie vorhanden. Bitte wende dich an einen Administrator.
				</p>
			{/if}
		{/if}
	</div>

	{#if !showMoreDetails}
		<button type="button" class="more-details-toggle" onclick={() => (showMoreDetails = true)}>
			<Icon name="plus" /> Mehr Details (Beschreibung, Zeiten, Notizen){hasMoreDetails
				? ' – ausgefüllt'
				: ''}
		</button>
	{:else}
		<div class="field">
			<label for="summary">Kurzbeschreibung</label>
			<textarea id="summary" bind:value={form.summary} rows="2" maxlength="500"></textarea>
		</div>

		<div class="field">
			<label for="preparation-days">Verteilt über … Tage</label>
			<input
				id="preparation-days"
				type="number"
				min="1"
				max="14"
				step="1"
				required
				bind:this={daysInput}
				value={form.preparation_days}
				aria-invalid={daysError ? 'true' : undefined}
				aria-describedby={daysError ? 'preparation-days-error' : undefined}
				oninput={(e) => validateDays(e.currentTarget)}
				oninvalid={(e) => validateDays(e.currentTarget)}
				onchange={(e) => changeDays(e.currentTarget)}
			/>
			{#if daysError}<p id="preparation-days-error" class="alert alert-error" role="alert">{daysError}</p>{/if}
		</div>
		{#if form.preparation_days > 1}
			<fieldset class="day-titles">
				<legend>Namen der Tage (optional)</legend>
				{#each dayNumbers as day}
					<input
						type="text"
						maxlength="100"
						aria-label={`Name von Tag ${day}`}
						placeholder={`Tag ${day}`}
						value={form.day_titles?.[day - 1] ?? ''}
						oninput={(e) => setDayTitle(day, e.currentTarget.value)}
					/>
				{/each}
			</fieldset>
		{/if}
		<div class="field-row">
			<TimeField id="prep-time" label="Arbeitszeit" bind:from={form.preparation_time} />
			<TimeField
				id="cook-time"
				label="Koch-/Backzeit"
				bind:from={form.cooking_time}
				bind:to={form.cooking_time_max}
				range
			/>
			<TimeField
				id="rest-time"
				label="Ruhezeit"
				bind:from={form.rest_time}
				bind:to={form.rest_time_max}
				range
			/>
			<div class="field">
				<label for="servings">Portionen</label>
				<input
					id="servings"
					type="number"
					min="1"
					value={form.servings ?? ''}
					oninput={(e) =>
						(form.servings = e.currentTarget.value ? Number(e.currentTarget.value) : null)}
				/>
			</div>
		</div>

		<div class="field">
			<label for="origin-person">Von wem stammt das Rezept?</label>
			<input
				id="origin-person"
				type="text"
				bind:value={form.origin_person}
				maxlength="150"
				placeholder="z. B. Oma Susi"
			/>
		</div>

		<div class="field">
			<label for="history">Geschichte zum Rezept</label>
			<textarea
				id="history"
				bind:value={form.history}
				rows="4"
				maxlength="5000"
				placeholder="Was verbindet euch mit diesem Rezept?"></textarea>
		</div>
		<div class="field">
			<label for="notes">Notizen</label>
			<textarea id="notes" bind:value={form.notes} rows="3" maxlength="4000"></textarea>
		</div>

		<div class="field">
			<label for="important-notes">Wichtiger Hinweis</label>
			<textarea
				id="important-notes"
				bind:value={form.important_notes}
				rows="2"
				maxlength="1000"
				placeholder="z. B. Allergene, kritische Schritte …"></textarea>
		</div>
	{/if}
</section>

<RecipeIngredientsEditor bind:ingredients={form.ingredients} bind:groups={form.ingredient_groups} />

<datalist id="recipe-days">
	{#if form.preparation_days > 1}{#each Array.from({ length: Math.min(14, Math.max(1, form.preparation_days || 1)) }, (_, i) => i + 1) as day}<option
				value={`Tag ${day}`}
			></option>{/each}{/if}
</datalist>
<section class="card form-section">
	<div class="section-header">
		<h2>Zubereitung</h2>
		<button type="button" class="btn btn-secondary btn-sm" onclick={addStep}
			><Icon name="plus" /> Schritt</button
		>
	</div>

	{#if form.steps.length === 0}
		<p class="muted">Noch keine Schritte hinzugefügt.</p>
	{/if}

	{#each form.steps as step, index (index)}
		<div class="list-row step-row">
			<div class="step-number">{index + 1}</div>
			<div class="list-row-fields step-fields">
				{#if step.heading !== null}
					<div class="step-heading-field">
						<input
							type="text"
							aria-label={`Abschnitt vor Schritt ${index + 1}`}
							placeholder="Abschnitt, z. B. Tag 1"
							list="recipe-days"
							maxlength="100"
							bind:value={form.steps[index].heading}
						/>
						<button
							type="button"
							class="more-details-toggle"
							onclick={() => (form.steps[index].heading = null)}
						>
							Abschnitt entfernen
						</button>
					</div>
				{:else}
					<button
						type="button"
						class="more-details-toggle"
						onclick={() => (form.steps[index].heading = '')}
					>
						<Icon name="plus" /> Abschnitt davor (z. B. Tag 1)
					</button>
				{/if}
				{#if form.preparation_days > 1}
					<select
						aria-label={`Tag von Schritt ${index + 1}`}
						value={step.day}
						onchange={(e) => (form.steps[index].day = Number(e.currentTarget.value))}
					>
						{#each dayNumbers as day}<option value={day}>Tag {day}</option>{/each}
					</select>
				{/if}
				<textarea
					aria-label={`Anweisung für Schritt ${index + 1}`}
					placeholder="Anweisung *"
					required
					rows="3"
					bind:value={form.steps[index].instruction}></textarea>

				{#if openStepDetails.has(index)}
					<div class="step-sub-fields">
						<label class="checkbox">
							<input type="checkbox" bind:checked={form.steps[index].is_important} />
							Wichtig
						</label>
						<input
							type="number"
							min="1"
							max="20160"
							step="1"
							aria-label={`Dauer von Schritt ${index + 1} in Minuten`}
							placeholder="Dauer (Min.)"
							value={step.duration_minutes ?? ''}
							oninput={(e) => setStepDuration(index, e.currentTarget.value)}
						/>
						<select
							aria-label={`Zeitart von Schritt ${index + 1}`}
							disabled={step.duration_minutes === null}
							bind:value={form.steps[index].time_kind}
						>
							<option value="preparation">Arbeitszeit</option>
							<option value="cooking">Koch-/Backzeit</option>
							<option value="rest">Ruhezeit</option>
						</select>
					</div>
					<input
						type="text"
						aria-label={`Notiz zu Schritt ${index + 1}`}
						placeholder="Notiz"
						bind:value={form.steps[index].note}
					/>
				{:else}
					<button
						type="button"
						class="more-details-toggle step-details-toggle"
						onclick={() => toggleStepDetails(index)}
					>
						<Icon name="plus" /> Details (Wichtig, Zeit, Notiz){stepHasDetails(step)
							? ' – ausgefüllt'
							: ''}
					</button>
				{/if}
			</div>
			<div class="list-row-actions">
				<button
					type="button"
					class="icon-btn"
					aria-label="Schritt nach oben verschieben"
					title="Nach oben"
					onclick={() => moveStep(index, -1)}
					disabled={index === 0}><Icon name="up" /></button
				>
				<button
					type="button"
					class="icon-btn"
					aria-label="Schritt nach unten verschieben"
					title="Nach unten"
					onclick={() => moveStep(index, 1)}
					disabled={index === form.steps.length - 1}><Icon name="down" /></button
				>
				<button
					type="button"
					class="icon-btn danger"
					aria-label="Schritt entfernen"
					title="Entfernen"
					onclick={() => removeStep(index)}><Icon name="close" /></button
				>
			</div>
		</div>
	{/each}
</section>

{#if pendingDays !== null}
	<Modal title="Schritte neu zuordnen" onclose={cancelReassignment}>
		<p class="muted">
			Für {pendingDays === 1 ? 'einen Tag' : `${pendingDays} Tage`} müssen diese Schritte einem verbleibenden
			Tag zugeordnet werden. Die Namen der entfallenden Tage werden entfernt.
		</p>
		{#each affectedSteps as index}
			<div class="field">
				<label for={`reassign-${index}`}>Neuer Tag für Schritt {index + 1}</label>
				<select
					id={`reassign-${index}`}
					value={reassignments[index] ?? ''}
					onchange={(e) => (reassignments[index] = Number(e.currentTarget.value))}
				>
					<option value="" disabled>Tag wählen</option>
					{#each Array.from({ length: pendingDays }, (_, i) => i + 1) as day}
						<option value={day}>Tag {day}</option>
					{/each}
				</select>
				<small class="muted">{form.steps[index].instruction.slice(0, 80)}</small>
			</div>
		{/each}
		<div class="modal-actions">
			<button type="button" class="btn btn-secondary" onclick={cancelReassignment}>Abbrechen</button
			>
			<button
				type="button"
				class="btn btn-primary"
				disabled={affectedSteps.some((index) => !reassignments[index])}
				onclick={confirmReassignment}>Zuordnung übernehmen</button
			>
		</div>
	</Modal>
{/if}

{#if pendingRemoval}
	<Modal
		title="Schritt entfernen?"
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

	.step-details-toggle {
		width: auto;
		margin-top: 0.1rem;
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

	.step-fields input,
	.step-fields textarea {
		background: var(--color-surface-raised);
		border: 1px solid var(--color-border-input);
		border-radius: var(--radius-sm);
		padding: 0.5em 0.65em;
		width: 100%;
	}

	.step-row {
		align-items: start;
	}

	.step-number {
		min-width: 1.5rem;
		flex-shrink: 0;
		font-family: var(--font-heading);
		font-size: var(--text-xl);
		line-height: 44px;
		color: var(--color-primary);
		font-variant-numeric: tabular-nums;
	}

	.step-fields {
		gap: 0.5rem;
	}

	.step-sub-fields {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 110px), 1fr));
		gap: 0.5rem;
		align-items: center;
	}

	.checkbox {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		min-height: 44px;
		font-size: var(--text-sm);
		font-weight: 600;
	}

	.checkbox input {
		width: auto;
	}

	.list-row-actions {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		flex-shrink: 0;
		flex-wrap: wrap;
		max-width: 100%;
	}

	@media (max-width: 640px) {

		/* Fields get the full width; the row actions sit on their own line. */
		.list-row {
			flex-wrap: wrap;
		}

		.list-row-fields {
			flex-basis: 100%;
		}

		.list-row-actions {
			flex-direction: row;
			margin-left: auto;
		}

		/* Keep controls on their own line instead of overlapping input hints at 200% zoom. */
		.step-row .list-row-actions {
			order: 1;
		}

		.step-row .list-row-fields {
			order: 2;
		}
	}
</style>
