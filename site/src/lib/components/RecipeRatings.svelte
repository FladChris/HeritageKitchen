<script lang="ts">
	import { onMount } from 'svelte';
	import * as api from '$lib/api';
	import Icon from './Icon.svelte';
	import Modal from './Modal.svelte';
	import { auth } from '$lib/stores/auth.svelte';
	import type { RecipeRatingSummary } from '$lib/types';

	let { recipeId, readOnly = false }: { recipeId: number; readOnly?: boolean } = $props();
	const stars = [1, 2, 3, 4, 5];
	const formatter = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 1 });
	const ratingName = $props.id();
	let summary = $state<RecipeRatingSummary>();
	let selection = $state<number>();
	let open = $state(false);
	let busy = $state(false);
	let error = $state('');
	let feedback = $state('');
	const mayRate = $derived(!readOnly && auth.user?.is_active);
	const ownRating = $derived(
		summary?.ratings.find(({ username }) => username === auth.user?.username)?.stars
	);
	const averageLabel = $derived(summary?.average == null
		? 'Noch nicht bewertet'
		: `${formatter.format(summary.average)} von 5 (${summary.count} ${summary.count === 1 ? 'Bewertung' : 'Bewertungen'})`);

	onMount(() => {
		void load();
	});

	async function load() {
		error = '';
		try {
			summary = await api.getRecipeRatings(recipeId);
		} catch {
			error = 'Bewertungen konnten nicht geladen werden.';
		}
	}

	function openRating() {
		selection = ownRating;
		error = '';
		open = true;
	}

	function closeRating() {
		if (busy) return;
		error = '';
		open = false;
	}

	async function changeRating(value: number | null) {
		if (!mayRate || busy) return;
		busy = true;
		error = '';
		feedback = '';
		try {
			summary = value === null
				? await api.removeRecipeRating(recipeId)
				: await api.saveRecipeRating(recipeId, value);
			open = false;
			feedback = value === null ? 'Bewertung entfernt.' : 'Bewertung gespeichert.';
		} catch {
			error = value === null
				? 'Bewertung konnte nicht entfernt werden.'
				: 'Bewertung konnte nicht gespeichert werden.';
		} finally {
			busy = false;
		}
	}
</script>

{#snippet star(fill: number)}
	<span class="star" aria-hidden="true">
		<Icon name="star" />
		<span class="fill" style:clip-path={`inset(0 ${100 - Math.max(0, Math.min(fill, 1)) * 100}% 0 0)`}>
			<Icon name="star" filled />
		</span>
	</span>
{/snippet}

{#snippet averageStars()}
	{#each stars as index (index)}
		{@render star((summary?.average ?? 0) - index + 1)}
	{/each}
{/snippet}

<section class="recipe-ratings no-print" aria-label="Rezeptbewertungen">
	{#if summary}
		{#if mayRate}
			<button class="rating-trigger" type="button" aria-haspopup="dialog"
				aria-label={`Rezept bewerten: ${averageLabel}`} title={averageLabel} onclick={openRating}>
				{@render averageStars()}
			</button>
		{:else}
			<div class="average" role="img" aria-label={averageLabel} title={averageLabel}>
				{@render averageStars()}
			</div>
		{/if}
	{:else if error}
		<p class="alert alert-error" role="alert">{error}</p>
		<button class="btn btn-secondary" type="button" onclick={load}>Erneut versuchen</button>
	{:else}
		<p role="status">Bewertungen werden geladen …</p>
	{/if}
	<p class="sr-only" role="status">{feedback}</p>
</section>

{#if open && mayRate}
	<Modal title="Rezept bewerten" onclose={closeRating}>
		<form onsubmit={(event) => {
			event.preventDefault();
			if (selection !== undefined && selection !== ownRating) void changeRating(selection);
		}}>
			<fieldset disabled={busy}>
				<legend>Wie hat es dir geschmeckt?</legend>
				<div class="choices">
					{#each stars as index (index)}
						<div class="choice">
							{@render star((selection ?? 0) - index + 1)}
							{#each (index === 1 ? [index] : [index - 0.5, index]) as value (value)}
								<label class:half={index > 1}>
									<input class="sr-only" type="radio" name={ratingName} {value} bind:group={selection} />
									<span class="sr-only">{formatter.format(value)} {value === 1 ? 'Stern' : 'Sterne'}</span>
								</label>
							{/each}
						</div>
					{/each}
				</div>
			</fieldset>
			{#if error}<p class="alert alert-error" role="alert">{error}</p>{/if}
			<div class="modal-actions">
				{#if ownRating !== undefined}
					<button class="btn btn-quiet" type="button" disabled={busy} onclick={() => changeRating(null)}>
						Bewertung entfernen
					</button>
				{/if}
				<button class="btn btn-secondary" type="button" disabled={busy} onclick={closeRating}>Abbrechen</button>
				<button class="btn btn-primary" disabled={busy || selection === undefined || selection === ownRating}>
					Bewerten
				</button>
			</div>
		</form>
	</Modal>
{/if}

<style>
	.recipe-ratings {
		margin-block: 0.25rem 1rem;
	}
	.average,
	.rating-trigger,
	.choices {
		display: inline-flex;
		gap: 0.2rem;
		color: var(--color-favorite);
	}
	.rating-trigger {
		border: 0;
		border-radius: var(--radius-sm);
		background: none;
		padding: 0.25rem;
		min-height: 2rem;
		cursor: pointer;
	}
	.star {
		display: grid;
		position: relative;
		place-items: center;
	}
	.star :global(.icon) {
		width: 1.25rem;
		height: 1.25rem;
	}
	.fill {
		position: absolute;
		display: grid;
		inset: 0;
		place-items: center;
	}
	fieldset {
		border: 0;
		padding: 0;
		margin: 0;
		min-width: 0;
	}
	.choices {
		gap: 0;
		margin-block: 0.5rem;
	}
	.choice {
		display: grid;
		grid-template-columns: 1fr 1fr;
		position: relative;
		width: clamp(2.25rem, 12vw, 3rem);
		height: 3rem;
	}
	.choice > .star {
		position: absolute;
		inset: 0;
		pointer-events: none;
	}
	.choice .star :global(.icon) {
		width: 1.75rem;
		height: 1.75rem;
	}
	.choice label {
		position: relative;
		grid-column: span 2;
		cursor: pointer;
	}
	.choice label.half {
		grid-column: span 1;
	}
	.choice label:has(input:focus-visible) {
		outline: 2px solid var(--color-focus);
		outline-offset: -2px;
	}
</style>
