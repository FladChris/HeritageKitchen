<script lang="ts">
	import { offline } from '$lib/stores/offline.svelte';
	import { offlineImage } from '$lib/offline/installed';
	import { page } from '$app/state';
	import { goto, pushState } from '$app/navigation';
	import { onMount } from 'svelte';
	import * as api from '$lib/api';
	import { ApiError } from '$lib/api';
	import { downloadBlob } from '$lib/download';
	import { auth } from '$lib/stores/auth.svelte';
	import { cookbook } from '$lib/stores/settings.svelte';
	import type { Recipe } from '$lib/types';
	import { ingredientAmount, recipeText } from '$lib/recipe-text';
	import { formatRange } from '$lib/format-time';
	import { stepGroups } from '$lib/recipe-days';
	import { effectiveTimes, replacedTimeNotices, timeLabels } from '$lib/recipe-times';
	import { keepScreenAwake } from '$lib/wake-lock';
	import { swipeDirection, wrappedIndex } from '$lib/photo-gestures';
	import PageToolbar from '$lib/components/PageToolbar.svelte';
	import PhotoViewer from '$lib/components/PhotoViewer.svelte';
	import RecipeComments from '$lib/components/RecipeComments.svelte';
	import RecipeRatings from '$lib/components/RecipeRatings.svelte';
	import Icon from '$lib/components/Icon.svelte';

	const recipeId = $derived(Number(page.params.id));
	const cooking = $derived(!!page.state.cooking);
	const photoOpen = $derived(!!page.state.photo);
	let recipe = $state<Recipe | null>(null);
	let mounted = $state(false);
	let loading = $state(true);
	let error = $state('');
	let actionError = $state('');
	let requestId = 0;
	let activeImageIndex = $state(0);
	const images = $derived(recipe?.images ?? []);
	const galleryImageId = $props.id();
	let favoriteId = $state<number | null>(null);
	let favoriteBusy = $state(false);
	let favoriteGeneration = 0;
	let factor = $state(1);
	let factorInput = $state('1');
	let portionsInput = $state('');
	let amountError = $state(false);
	let status = $state('');
	const savedNotice = $derived(page.url.searchParams.get('saved') === 'created'
		? 'Rezept wurde gespeichert.'
		: page.url.searchParams.get('saved') === 'updated' ? 'Änderungen wurden gespeichert.' : '');
	let exporting = $state(false);
	let copyTimer: ReturnType<typeof setTimeout>;
	let checkedIngredients = $state(new Set<number>());
	let checkedSteps = $state(new Set<number>());
	let swipeStart: { id: number; x: number; y: number } | null = null;
	let suppressGalleryClick = false;
	const whatsappHref = $derived(
		recipe ? `https://wa.me/?text=${encodeURIComponent(recipeText(recipe, factor))}` : ''
	);
	const returnTo = $derived(page.url.searchParams.get('returnTo'));
	const overview = $derived(
		returnTo === '/' || returnTo === '/favorites' || returnTo?.startsWith('/?') ? returnTo : null
	);
	const backHref = $derived(overview ?? (recipe?.category ? `/?category=${recipe.category.id}` : '/'));
	const backLabel = $derived(overview ? 'Zurück zur Übersicht' : recipe?.category?.name ?? 'Alle Rezepte');
	const sortedIngredients = $derived(
		recipe ? [...recipe.ingredients].sort((a, b) => a.position - b.position) : []
	);
	const ingredientGroups = $derived(
		recipe
			? [
					...(recipe.ingredients.some((ingredient) => ingredient.group_position === null)
						? [{ position: null, name: '' }]
						: []),
					...recipe.ingredient_groups.slice().sort((a, b) => a.position - b.position)
				]
			: []
	);
	const dayGroups = $derived(recipe ? stepGroups(recipe) : []);
	const sortedSteps = $derived(dayGroups.flatMap((group) => group.steps));
	const dayStarts = $derived(new Map(dayGroups.map((group) => [group.steps[0].id, group.label])));
	const quantityLabel = $derived(
		`${((recipe?.servings ?? 1) * factor).toLocaleString('de-DE', { maximumFractionDigits: 3 })} Portionen`
	);
	const servingsFact = $derived(recipe?.servings ? `Für ${quantityLabel}` : '');
	const times = $derived(recipe ? effectiveTimes(recipe) : null);
	const timeNotices = $derived(
		recipe && page.url.searchParams.get('timenotice') ? replacedTimeNotices(recipe) : []
	);
	const facts = $derived(
		recipe && times
			? [
					recipe.preparation_days > 1 ? `Über ${recipe.preparation_days} Tage` : servingsFact,
					times.preparation ? `${formatRange(times.preparation.from, null)} Arbeit` : '',
					times.rest ? `${formatRange(times.rest.from, times.rest.to)} Ruhezeit` : '',
					times.cooking
						? `${formatRange(times.cooking.from, times.cooking.to)} Koch-/Backzeit`
						: '',
					times.total
						? `Summe der erfassten Zeiten: ${formatRange(times.total.from, times.total.to)}`
						: '',
					recipe.preparation_days > 1 ? servingsFact : ''
				]
					.filter(Boolean)
					.join(' · ')
			: ''
	);

	function setFactor(value: number) {
		factor = value;
		factorInput = String(value).replace('.', ',');
		portionsInput = ((recipe?.servings ?? 1) * value).toLocaleString('de-DE', {
			maximumFractionDigits: 3
		});
		amountError = false;
	}
	function changeAmount(value: string, usePortions = false) {
		if (usePortions) portionsInput = value;
		else factorInput = value;
		const number = Number(value.replace(',', '.'));
		amountError = !/^\d+(?:[,.]\d*)?$/.test(value) || !Number.isFinite(number) || number <= 0;
		if (amountError) return;
		factor = usePortions ? number / (recipe?.servings ?? 1) : number;
		if (usePortions) factorInput = factor.toLocaleString('de-DE', { maximumFractionDigits: 4 });
		else portionsInput = ((recipe?.servings ?? 1) * factor).toLocaleString('de-DE', {
			maximumFractionDigits: 3
		});
	}
	function showImage(delta: number) {
		activeImageIndex = wrappedIndex(activeImageIndex, delta, images.length);
	}
	function galleryDown(event: PointerEvent & { currentTarget: HTMLButtonElement }) {
		if (!event.isPrimary || event.button !== 0 || swipeStart) return;
		swipeStart = { id: event.pointerId, x: event.clientX, y: event.clientY };
		suppressGalleryClick = false;
		event.currentTarget.setPointerCapture(event.pointerId);
	}
	function galleryUp(event: PointerEvent) {
		if (swipeStart?.id !== event.pointerId) return;
		const dx = event.clientX - swipeStart.x;
		const dy = event.clientY - swipeStart.y;
		swipeStart = null;
		suppressGalleryClick = Math.hypot(dx, dy) >= 10;
		const direction = swipeDirection(dx, dy, 1);
		if (images.length > 1 && direction) showImage(direction);
	}
	function cancelGallerySwipe() {
		swipeStart = null;
		suppressGalleryClick = true;
	}
	function galleryPointerInterrupted(event: PointerEvent) {
		if (swipeStart?.id === event.pointerId) cancelGallerySwipe();
	}
	function galleryAdditionalPointer(event: PointerEvent) {
		if (swipeStart && swipeStart.id !== event.pointerId && event.button === 0) {
			cancelGallerySwipe();
		}
	}
	function galleryKeydown(event: KeyboardEvent) {
		if (images.length < 2 || (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight')) return;
		event.preventDefault();
		showImage(event.key === 'ArrowLeft' ? -1 : 1);
	}
	function galleryClick(event: MouseEvent & { currentTarget: HTMLButtonElement }) {
		if (suppressGalleryClick && event.detail > 0) return;
		event.currentTarget.focus({ preventScroll: true });
		openPhoto();
	}
	function toggleCheck(kind: 'ingredient' | 'step', id: number) {
		const next = new Set(kind === 'ingredient' ? checkedIngredients : checkedSteps);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		if (kind === 'ingredient') checkedIngredients = next;
		else checkedSteps = next;
	}
	async function load(id: number) {
		const generation = ++requestId;
		favoriteGeneration++;
		favoriteId = null;
		favoriteBusy = false;
		loading = true;
		error = '';
		recipe = null;
		try {
			const result = await api.getRecipe(id);
			if (generation !== requestId) return;
			recipe = result;
			activeImageIndex = 0;
			setFactor(1);
		} catch (err) {
			if (generation === requestId)
				error =
					err instanceof ApiError && err.status === 404
						? 'Dieses Rezept wurde nicht gefunden.'
						: 'Rezept konnte nicht geladen werden.';
		} finally {
			if (generation === requestId) loading = false;
		}
	}
	function isCurrentFavorite(id: number, generation: number, userId: number) {
		return recipeId === id && generation === favoriteGeneration && auth.user?.id === userId;
	}

	async function refreshFavoriteStatus(id: number) {
		const userId = auth.user?.id;
		const generation = ++favoriteGeneration;
		favoriteId = null;
		favoriteBusy = false;
		if (userId === undefined) return;
		favoriteBusy = true;
		try {
			const favorites = await api.listFavorites(undefined, userId);
			if (isCurrentFavorite(id, generation, userId))
				favoriteId = favorites.find((favorite) => favorite.recipe_id === id)?.id ?? null;
		} catch (err) {
			if (
				isCurrentFavorite(id, generation, userId) &&
				err instanceof ApiError &&
				(err.status === 401 || err.status === 403)
			) {
				void auth.refresh();
			}
		} finally {
			if (isCurrentFavorite(id, generation, userId)) favoriteBusy = false;
		}
	}
	async function toggleFavorite() {
		if (favoriteBusy) return;
		const userId = auth.user?.id;
		if (userId === undefined) {
			goto('/login');
			return;
		}
		favoriteBusy = true;
		const id = recipeId;
		const generation = ++favoriteGeneration;
		const previousFavorite = favoriteId;
		actionError = '';
		try {
			let result: number | null = null;
			if (previousFavorite) await api.removeFavorite(previousFavorite, userId);
			else result = (await api.addFavorite(id, userId)).id;
			if (isCurrentFavorite(id, generation, userId)) favoriteId = result;
		} catch (err) {
			if (!isCurrentFavorite(id, generation, userId)) return;
			if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
				favoriteId = null;
				void auth.refresh();
			} else {
				actionError = 'Favorit konnte nicht aktualisiert werden.';
			}
		} finally {
			if (isCurrentFavorite(id, generation, userId)) favoriteBusy = false;
		}
	}
	async function copy(text: string, message: string) {
		actionError = '';
		status = '';
		clearTimeout(copyTimer);
		try {
			if (navigator.clipboard) await navigator.clipboard.writeText(text);
			else {
				const input = document.createElement('textarea');
				input.value = text;
				input.style.position = 'fixed';
				input.style.opacity = '0';
				document.body.appendChild(input);
				const previous = document.activeElement as HTMLElement | null;
				try {
					input.select();
					if (!document.execCommand('copy')) throw new Error('Copy failed');
				} finally {
					input.remove();
					previous?.focus({ preventScroll: true });
				}
			}
			status = message;
			copyTimer = setTimeout(() => {
				status = '';
			}, 3000);
		} catch {
			actionError = 'Kopieren ist fehlgeschlagen. Bitte versuch es erneut.';
		}
	}
	function closeActions(menu: HTMLDetailsElement) {
		menu.open = false;
		menu.querySelector('summary')?.focus({ preventScroll: true });
	}
	function actionsKeydown(event: KeyboardEvent & { currentTarget: HTMLDetailsElement }) {
		if (event.key !== 'Escape' || !event.currentTarget.open) return;
		event.preventDefault();
		closeActions(event.currentTarget);
	}
	async function downloadPdf() {
		const currentRecipe = recipe;
		if (!currentRecipe || exporting) return;
		exporting = true;
		actionError = '';
		try {
			const query = new URLSearchParams({
				factor: String(Number(factor.toFixed(4)))
			});
			const response = await fetch(`/api/recipes/${currentRecipe.id}/pdf?${query}`, {
				credentials: 'include',
				cache: 'no-store'
			});
			if (!response.ok || !response.headers.get('content-type')?.includes('application/pdf'))
				throw new Error('PDF failed');
			downloadBlob(await response.blob(), `${currentRecipe.title.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '-').trim() || 'Rezept'}.pdf`);
		} catch {
			actionError = 'Das PDF konnte nicht gespeichert werden.';
		} finally {
			exporting = false;
		}
	}
	function startCooking() {
		pushState('', { ...page.state, cooking: true });
	}
	function openPhoto() {
		pushState('', { ...page.state, photo: true });
	}
	function closeMode() {
		history.back();
	}
	onMount(() => {
		mounted = true;
		return () => clearTimeout(copyTimer);
	});
	$effect(() => {
		void offline.generation;
		if (mounted) void load(recipeId);
	});
	$effect(() => {
		if (recipe && !auth.loading) void refreshFavoriteStatus(recipe.id);
	});
	$effect(() => {
		if (!mounted || !cooking) {
			checkedIngredients = new Set();
			checkedSteps = new Set();
			return;
		}
		const request =
			'wakeLock' in navigator ? () => navigator.wakeLock.request('screen') : undefined;
		// Without a wake lock (older browsers, plain HTTP) cooking mode simply works without it.
		return keepScreenAwake(request, document, () => {});
	});
</script>

<svelte:window onpointerdown={galleryAdditionalPointer} onpointerup={galleryPointerInterrupted} />

<svelte:head
	><title>{recipe ? `${recipe.title} · ` : ''}{cookbook.settings.cookbook_name}</title></svelte:head
>
{#if loading}<div class="skeleton" style="height: 200px;"></div>
{:else if error}<PageToolbar {backHref} {backLabel} />
	<p class="alert alert-error" role="alert">{error}</p>
{:else if recipe}
	{#if !cooking}<PageToolbar {backHref} {backLabel} />{/if}
	<article class="recipe-detail" class:cooking>
		{#if cooking}<div class="cooking-bar no-print">
				<strong>Kochmodus</strong><button class="btn btn-secondary" onclick={closeMode}
					>Kochmodus beenden</button
				>
			</div>{/if}
		<header class="recipe-heading">
			<h1 class="display">{recipe.title}</h1>
			{#if recipe.origin_person}<p class="source">von {recipe.origin_person}</p>{/if}
			{#if !cooking}
				{#key `${recipe.id}:${offline.generation}:${offline.offline}`}
					<RecipeRatings recipeId={recipe.id} readOnly={offline.offline} />
				{/key}
			{/if}
			{#if recipe.history}<p class="story">{recipe.history}</p>{/if}
			{#if recipe.summary}<p class="summary">{recipe.summary}</p>{/if}
			{#if facts}<p class="facts">{facts}</p>{/if}
		</header>
		{#if savedNotice}<p class="alert alert-success no-print" role="status">{savedNotice}</p>{/if}
		{#each timeNotices as notice}<p class="alert alert-success no-print" role="status">
				{notice}
			</p>{/each}
		{#if !cooking && images.length}
			<div class="gallery no-print" role="group" aria-label="Rezeptbilder">
				<button
					class="photo-button"
					onclick={galleryClick}
					onkeydown={galleryKeydown}
					onpointerdown={galleryDown}
					onpointerup={galleryUp}
					onpointercancel={galleryPointerInterrupted}
					onlostpointercapture={galleryPointerInterrupted}
					aria-label="Foto vergrößern"
					aria-describedby={galleryImageId}
					title="Foto vergrößern"
				>
					{#key activeImageIndex}
						<img
							id={galleryImageId}
							src={offlineImage(images[activeImageIndex].file_path)}
							alt={images[activeImageIndex].alt_text ?? recipe.title}
							draggable="false"
						/>
					{/key}
				</button>
				{#if images.length > 1}
					<button
						class="icon-btn gallery-arrow previous"
						onclick={() => showImage(-1)}
						onkeydown={galleryKeydown}
						aria-label="Vorheriges Bild"
						title="Vorheriges Bild"><Icon name="previous" /></button
					>
					<button
						class="icon-btn gallery-arrow next"
						onclick={() => showImage(1)}
						onkeydown={galleryKeydown}
						aria-label="Nächstes Bild"
						title="Nächstes Bild"><Icon name="next" /></button
					>
					<span class="gallery-counter" aria-hidden="true">{activeImageIndex + 1} / {images.length}</span>
					<span class="sr-only" role="status">Bild {activeImageIndex + 1} von {images.length}</span>
				{/if}
			</div>
		{/if}
		{#if !cooking}
			<div class="actions no-print">
				<div class="primary-actions">
					<button class="btn btn-primary" onclick={startCooking}>Kochmodus</button><button
						class="btn btn-secondary favorite"
						onclick={toggleFavorite}
						disabled={favoriteBusy || offline.offline}
						aria-pressed={!!favoriteId}
						><Icon name="star" filled={!!favoriteId} />{favoriteId ? 'Gemerkt' : 'Merken'}</button
					>
					{#if auth.hasRole('editor')}<a class="btn btn-quiet" href={`/recipes/${recipe.id}/edit${overview ? `?returnTo=${encodeURIComponent(overview)}` : ''}`}
							><Icon name="edit" /> Bearbeiten</a
						>{/if}
				</div>
				<div class="share-actions" aria-label="Rezept weitergeben">
					<a
						class="btn btn-quiet"
						href={whatsappHref}
						target="_blank"
						rel="noopener noreferrer">Per WhatsApp teilen</a
					>
					<button
						class="btn btn-quiet"
						onclick={() => copy(recipeText(recipe!, factor), 'Rezepttext kopiert.')}
						>Text kopieren</button
					>
					<!-- svelte-ignore a11y_no_noninteractive_element_interactions (Escape bubbles from the summary and action buttons.) -->
					<details class="more-actions" onkeydown={actionsKeydown}>
						<summary class="btn btn-quiet">Weitere Aktionen <Icon name="expand" /></summary>
						<div class="action-menu">
							<button
								onclick={(event) => {
									const menu = event.currentTarget.closest('details');
									if (menu) closeActions(menu);
									void copy(window.location.href, 'Link kopiert.');
								}}>Link kopieren</button
							>
							<button onclick={() => window.print()}>Drucken</button>
							<button onclick={downloadPdf} disabled={exporting} aria-busy={exporting}
								>{exporting ? 'PDF wird geladen …' : 'Als PDF speichern'}</button
							>
						</div>
					</details>
				</div>
			</div>
			<p class="copy-status no-print" role="status" aria-live="polite">{status}</p>
			{#if actionError}<p class="alert alert-error no-print" role="alert">{actionError}</p>{/if}
		{/if}
		{#if recipe.important_notes}<aside class="note">
				<h2>Wichtiger Hinweis</h2>
				<p>{recipe.important_notes}</p>
			</aside>{/if}
		<div class="recipe-columns">
			<section class="ingredients" aria-labelledby="ingredients-heading">
				<h2 id="ingredients-heading">Zutaten</h2>
				{#if factor !== 1 || cooking}<p class="quantity">
						{quantityLabel}{factor !== 1 ? ' (angepasst)' : ''}
					</p>{/if}
				{#if sortedIngredients.length === 0}<p>Keine Zutaten hinterlegt.</p>{:else}
					{#if !cooking}<details class="portion-details no-print">
							<summary>Menge anpassen</summary>
							<div class="portion-calculator">
								<div class="field">
									<label for="portion-factor">Faktor</label><input
										id="portion-factor"
										inputmode="decimal"
										value={factorInput}
										oninput={(event) => changeAmount(event.currentTarget.value)}
										aria-invalid={amountError}
									/>
								</div>
								<div class="field">
										<label for="portion-count">Gewünschte Portionen</label><input
											id="portion-count"
											inputmode="decimal"
											value={portionsInput}
											oninput={(event) => changeAmount(event.currentTarget.value, true)}
											aria-invalid={amountError}
										/>
									</div>
								<div class="portion-buttons">
									{#each [0.5, 1, 2, 3] as value}<button
											class="btn btn-secondary"
											onclick={() => setFactor(value)}
											aria-pressed={factor === value}>{value.toLocaleString('de-DE')}-fach</button
										>{/each}<button
										class="btn btn-secondary"
										onclick={() => setFactor(1)}
										disabled={factor === 1}>Zurücksetzen</button
									>
								</div>
								{#if amountError}<p role="alert">Bitte eine Zahl größer als 0 eingeben.</p>{/if}
							</div>
						</details>{/if}
					{#each ingredientGroups as group (group.position)}
						{#if group.name}<h3 class="group-title">{group.name}</h3>{/if}
						<ul class="ingredient-list">
							{#each sortedIngredients.filter((ingredient) => ingredient.group_position === group.position) as ingredient (ingredient.id)}
								<li class:checked={cooking && checkedIngredients.has(ingredient.id)}>
									{#if cooking}<label class="ingredient-check"
											><input
												type="checkbox"
												checked={checkedIngredients.has(ingredient.id)}
												onchange={() => toggleCheck('ingredient', ingredient.id)}
											/><span class="ingredient-amount">{ingredientAmount(ingredient, factor)}</span
											><span
												>{ingredient.name}{#if ingredient.note}<small>
														– {ingredient.note}</small
													>{/if}</span
											></label
										>
									{:else}<span class="ingredient-amount"
											>{ingredientAmount(ingredient, factor)}</span
										><span
											>{ingredient.name}{#if ingredient.note}<small>
													– {ingredient.note}</small
												>{/if}</span
										>{/if}
								</li>
							{/each}
						</ul>
					{/each}
				{/if}
			</section>
			<section class="steps" aria-labelledby="steps-heading">
				<h2 id="steps-heading">Zubereitung</h2>
				{#if !sortedSteps.length}<p>Keine Zubereitungsschritte hinterlegt.</p>{/if}
				{#each sortedSteps as step, index (step.id)}
					<div class="print-step">
						{#if dayStarts.get(step.id)}<h3 class="step-heading day-heading">
								{dayStarts.get(step.id)}
							</h3>{/if}
						{#if step.heading}<h3
								class="step-heading"
								class:day-heading={recipe.preparation_days > 1}
							>
								{step.heading}
							</h3>{/if}
						<div
							class="step"
							class:important={step.is_important}
							class:checked={cooking && checkedSteps.has(step.id)}
						>
							<span class="step-number" aria-hidden="true">{index + 1}</span>
							<div class="step-text">
								{#if cooking}<label class="step-check"
										><input
											type="checkbox"
											checked={checkedSteps.has(step.id)}
											onchange={() => toggleCheck('step', step.id)}
										/><span>Schritt {index + 1} erledigt</span></label
									>{:else}<span class="sr-only">Schritt {index + 1}:</span>{/if}
								<p>{step.instruction}</p>
								{#if step.duration_minutes && step.time_kind}<p class="step-note">
										{timeLabels[step.time_kind]}: {formatRange(step.duration_minutes, null)}
									</p>{/if}
								{#if step.note}<p class="step-note">{step.note}</p>{/if}
							</div>
						</div>
					</div>
				{/each}
			</section>
		</div>
		{#if recipe.notes}<section class="extra">
				<h2>Notizen</h2>
				<p>{recipe.notes}</p>
			</section>{/if}
		{#if !cooking}
			{#key recipe.id}
				<RecipeComments recipeId={recipe.id} user={auth.user} />
			{/key}
		{/if}
	</article>
	{#if photoOpen && images.length}<PhotoViewer
			{images}
			bind:index={activeImageIndex}
			title={recipe.title}
			onclose={closeMode}
		/>{/if}
{/if}

<style>
	.favorite[aria-pressed='true'] :global(.icon) {
		color: var(--color-favorite);
	}
	.recipe-detail {
		max-width: 100%;
	}
	.recipe-heading,
	.note p,
	.extra p {
		max-width: var(--measure);
	}
	.source,
	.story,
	.summary,
	.note p,
	.extra p {
		font-family: var(--font-recipe);
		font-size: var(--text-reading);
		white-space: pre-line;
	}
	.recipe-heading h1:has(+ .source) {
		margin-bottom: 0.2rem;
	}
	.source {
		margin-block: 0 0.75rem;
		color: var(--color-text-secondary);
	}
	.facts {
		color: var(--color-text-secondary);
		font-size: var(--text-sm);
	}
	.gallery {
		position: relative;
		aspect-ratio: 16 / 10;
		max-height: 30rem;
		margin-block: 1rem 1.5rem;
	}
	.photo-button {
		position: absolute;
		inset: 0;
		background: var(--color-text);
		border: 0;
		border-radius: calc(3 * var(--radius-sm));
		box-shadow: 0 0.35rem 1.25rem rgb(0 0 0 / 14%);
		overflow: hidden;
		padding: 0;
		width: 100%;
		cursor: zoom-in;
		touch-action: pan-y pinch-zoom;
	}
	.photo-button img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
		pointer-events: none;
	}
	@media (prefers-reduced-motion: no-preference) {
		.photo-button img {
			animation: gallery-fade 180ms ease-out;
		}
	}
	@keyframes gallery-fade {
		from {
			opacity: 0.45;
		}
	}
	.gallery-arrow,
	.gallery-counter {
		position: absolute;
		color: var(--color-primary-contrast);
		background: rgb(0 0 0 / 65%);
		border-radius: 999px;
	}
	.gallery-arrow {
		top: 50%;
		transform: translateY(-50%);
		border: 0;
	}
	.gallery-arrow:hover,
	.gallery-arrow:focus-visible {
		background: var(--color-text);
	}
	.gallery-arrow:focus-visible {
		outline-color: var(--color-primary-contrast);
		outline-offset: -4px;
	}
	.gallery-arrow.previous {
		inset-inline-start: 0.5rem;
	}
	.gallery-arrow.next {
		inset-inline-end: 0.5rem;
	}
	.gallery-counter {
		inset-inline-end: 0.75rem;
		bottom: 0.75rem;
		padding: 0.15rem 0.6rem;
		font-size: var(--text-sm);
		font-variant-numeric: tabular-nums;
		pointer-events: none;
	}
	.actions {
		display: grid;
		gap: 0.25rem;
	}
	.primary-actions,
	.share-actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
	.share-actions {
		gap: 0;
		margin-left: -0.5em;
	}
	.more-actions {
		position: relative;
	}
	.more-actions summary {
		list-style: none;
	}
	.more-actions summary::-webkit-details-marker {
		display: none;
	}
	.more-actions[open] summary {
		background: var(--color-surface);
	}
	.more-actions[open] summary :global(.icon) {
		transform: rotate(180deg);
	}
	.action-menu {
		position: absolute;
		top: 100%;
		left: 0;
		z-index: 5;
		width: 16rem;
		border: 1px solid var(--color-border-input);
		border-radius: var(--radius-sm);
		background: var(--color-surface-raised);
	}
	.action-menu button {
		display: block;
		width: 100%;
		min-height: 44px;
		padding: 0.5em 0.9em;
		border: none;
		background: none;
		font-size: var(--text-sm);
		font-weight: 600;
		text-align: left;
	}
	.action-menu button + button {
		border-top: 1px solid var(--color-border-subtle);
	}
	.action-menu button:hover {
		background: var(--color-surface);
	}
	.copy-status {
		min-height: 1.5em;
		font-size: var(--text-sm);
		margin: 0.4rem 0;
	}
	.note {
		border-block: 1px solid var(--color-text);
		padding-block: 1rem;
		margin-block: 1.5rem;
	}
	.note h2 {
		font-family: var(--font-body);
		font-size: var(--text-base);
		font-weight: 600;
	}
	.note p {
		margin: 0;
	}
	.recipe-columns {
		display: grid;
		grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.4fr);
		gap: 3rem;
		margin-top: 1.5rem;
	}
	.ingredients {
		align-self: start;
		position: sticky;
		top: 6rem;
		max-height: calc(100dvh - 7rem);
		overflow-y: auto;
	}
	.quantity {
		color: var(--color-primary);
		font-size: var(--text-sm);
		margin-bottom: 0.5rem;
	}
	.portion-details {
		margin-bottom: 1rem;
	}
	.portion-details summary {
		color: var(--color-primary);
		font-size: var(--text-sm);
		font-weight: 600;
		cursor: pointer;
		padding-block: 0.65rem;
	}
	.portion-calculator {
		margin-top: 0.5rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}
	.portion-calculator .field {
		flex: 1;
		min-width: 100px;
		margin: 0;
	}
	.portion-calculator input {
		width: 100%;
	}
	.portion-buttons {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}
	.portion-buttons [aria-pressed='true'] {
		border-color: var(--color-primary);
		background: var(--color-surface);
	}
	.group-title {
		margin-top: 1.25rem;
	}
	.ingredient-list {
		margin: 0;
		padding: 0;
		list-style: none;
		font-family: var(--font-recipe);
		font-size: var(--text-reading);
	}
	.ingredient-list li {
		display: grid;
		grid-template-columns: 6rem minmax(0, 1fr);
		gap: 0.75rem;
		padding-block: 0.4rem;
		border-bottom: 1px solid var(--color-border-subtle);
	}
	.ingredient-amount {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	small {
		font-size: 0.9em;
		color: var(--color-text-secondary);
	}
	.step {
		display: flex;
		gap: 1rem;
		margin-bottom: 1.25rem;
	}
	.step-number {
		font-family: var(--font-heading);
		font-size: var(--text-xl);
		line-height: 1.3;
		color: var(--color-primary);
		min-width: 1.5rem;
		font-variant-numeric: tabular-nums;
	}
	.step-text {
		font-family: var(--font-recipe);
		font-size: var(--text-reading);
		line-height: 1.5;
		max-width: 65ch;
		white-space: pre-line;
		overflow-wrap: anywhere;
	}
	.step-text p {
		margin: 0 0 0.4rem;
	}
	.important .step-text > p:first-of-type {
		font-weight: 600;
	}
	.step-note {
		color: var(--color-text-secondary);
		font-size: 0.9em;
	}
	.step-heading {
		margin: 1.5rem 0 1rem;
	}
	.day-heading {
		padding-top: 1rem;
		border-top: 1px solid var(--color-text);
	}
	.extra {
		border-top: 1px solid var(--color-border);
		margin-top: 2rem;
		padding-top: 1rem;
	}
	@media screen {
		.cooking .story,
		.cooking .summary,
		.cooking .facts,
		.cooking .extra {
			display: none;
		}
	}
	.cooking-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		position: sticky;
		top: 0;
		background: var(--color-bg);
		z-index: 4;
		padding-block: 0.75rem;
		margin-bottom: 1rem;
		border-bottom: 1px solid var(--color-border);
	}
	.cooking h1 {
		font-size: clamp(2.5rem, 4vw, 4.0625rem);
	}
	.cooking .step-number {
		font-size: 2.25rem;
	}
	.cooking .quantity {
		font-size: var(--text-reading);
	}
	.cooking h2 {
		font-size: 2rem;
	}
	.cooking h3 {
		font-size: 1.5rem;
	}
	.cooking .step-text,
	.cooking .ingredient-list,
	.cooking .note p {
		font-size: 1.4375rem;
	}
	.cooking .ingredient-list li {
		display: block;
	}
	/* On phones the amount sits above the name so long units never run into the ingredient. */
	.ingredient-check {
		display: grid;
		grid-template-columns: 1.4rem minmax(0, 1fr);
		gap: 0 0.75rem;
		cursor: pointer;
		min-height: 44px;
		align-items: start;
	}
	.ingredient-check .ingredient-amount {
		grid-column: 2;
		text-align: left;
		font-weight: 600;
	}
	.ingredient-check .ingredient-amount:empty {
		display: none;
	}
	.ingredient-check > span:last-child {
		grid-column: 2;
	}
	.ingredient-check input,
	.step-check input {
		width: 1.25rem;
		height: 1.25rem;
		accent-color: var(--color-primary);
		margin-top: 0.4rem;
	}
	.step-check {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		font-family: var(--font-body);
		font-size: var(--text-base);
		min-height: 44px;
		cursor: pointer;
	}
	.checked .ingredient-check > span,
	.checked .step-text > p {
		text-decoration: line-through;
	}
	@media (min-width: 601px) {
		.ingredient-check {
			grid-template-columns: 1.4rem 9rem minmax(0, 1fr);
		}
		.ingredient-check .ingredient-amount {
			text-align: right;
			font-weight: inherit;
		}
		.ingredient-check > span:last-child {
			grid-column: 3;
		}
	}
	@media (max-width: 850px) {
		.recipe-columns {
			grid-template-columns: 1fr;
			gap: 2rem;
		}
		.ingredients {
			position: static;
			max-height: none;
			overflow: visible;
		}
		/* Always on its own row so the summary does not move when the menu opens. */
		.more-actions {
			flex-basis: 100%;
		}
		.action-menu {
			position: static;
			width: auto;
			margin: 0.25rem 0 0 0.5em;
		}
	}
</style>
