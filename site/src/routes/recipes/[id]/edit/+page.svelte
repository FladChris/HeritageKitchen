<script lang="ts">
	import { replacedTimeNotices } from '$lib/recipe-times';
	import { changedRecipeFields } from '$lib/recipe-conflicts';
	import { cookbook } from '$lib/stores/settings.svelte';
	import { page } from '$app/state';
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { guardUnsavedChanges } from '$lib/unsaved-changes';
	import * as api from '$lib/api';
	import { ApiError } from '$lib/api';
	import { auth } from '$lib/stores/auth.svelte';
	import type { Category, Recipe, RecipeConflict, RecipeConflictDetail, RecipeImage, RecipeInput } from '$lib/types';
	import RecipeFieldsForm from '$lib/components/RecipeFieldsForm.svelte';
	import RecipeConflictDialog from '$lib/components/RecipeConflictDialog.svelte';
	import RecipeImageManager from '$lib/components/RecipeImageManager.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import PageToolbar from '$lib/components/PageToolbar.svelte';

	const recipeId = $derived(Number(page.params.id));
	const returnTo = $derived(page.url.searchParams.get('returnTo'));
	const detailHref = $derived(
		`/recipes/${recipeId}${returnTo ? `?returnTo=${encodeURIComponent(returnTo)}` : ''}`
	);

	let categories = $state<Category[]>([]);
	let images = $state<RecipeImage[]>([]);
	let form = $state<RecipeInput | null>(null);
	let openedRecipe = $state<Recipe | null>(null);
	let baseVersion = $state<number | null>(null);
	let conflict = $state<RecipeConflict | null>(null);
	let showOverwriteConfirm = $state(false);
	let loading = $state(true);
	let saving = $state(false);
	let error = $state<string | null>(null);
	let justCreated = $state(false);
	let showDeleteConfirm = $state(false);
	let deleting = $state(false);
	let originalForm = $state('');
	let originalCategoryId = $state<number | null>(null);
	let allowNavigation = false;
	const dirty = $derived(form !== null && originalForm !== '' && JSON.stringify(form) !== originalForm);

	guardUnsavedChanges(() => allowNavigation || !dirty);

	function toForm(recipe: Recipe): RecipeInput {
		return {
			history: recipe.history,
			preparation_days: recipe.preparation_days,
			day_titles: recipe.day_titles,
			title: recipe.title,
			summary: recipe.summary,
			preparation_time: recipe.preparation_time,
			cooking_time: recipe.cooking_time,
			cooking_time_max: recipe.cooking_time_max,
			rest_time: recipe.rest_time,
			rest_time_max: recipe.rest_time_max,
			servings: recipe.servings,
			origin_person: recipe.origin_person,
			notes: recipe.notes,
			important_notes: recipe.important_notes,
			category_id: recipe.category_id,
			ingredients: [...recipe.ingredients]
				.sort((a, b) => a.position - b.position)
				.map((i) => ({
					position: i.position,
					group_position: i.group_position,
					name: i.name,
					amount: i.amount === null ? null : String(Number(i.amount)).replace('.', ','),
					unit: i.unit,
					note: i.note
				})),
			ingredient_groups: recipe.ingredient_groups.map((group) => ({
				position: group.position,
				name: group.name
			})),
			steps: [...recipe.steps]
				.sort((a, b) => a.position - b.position)
				.map((s) => ({
					position: s.position,
					instruction: s.instruction,
					heading: s.heading,
					is_important: s.is_important,
					note: s.note,
					duration_minutes: s.duration_minutes,
					time_kind: s.time_kind,
					day: s.day
				}))
		};
	}

	onMount(async () => {
		await auth.init();
		if (!auth.hasRole('editor')) {
			goto('/login');
			return;
		}
		justCreated = page.url.searchParams.get('created') === '1';
		loading = true;
		try {
			const [recipe, categoryList] = await Promise.all([
				api.getRecipe(recipeId),
				api.listCategories().catch(() => [] as Category[])
			]);
			form = toForm(recipe);
			originalForm = JSON.stringify(form);
			originalCategoryId = recipe.category_id;
			openedRecipe = structuredClone(recipe);
			baseVersion = recipe.version;
			images = recipe.images;
			categories = categoryList;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Rezept konnte nicht geladen werden.';
		} finally {
			loading = false;
		}
	});

	function isConflictDetail(value: unknown): value is RecipeConflictDetail {
		if (value === null || typeof value !== 'object') return false;
		const detail = value as Partial<RecipeConflictDetail>;
		return (
			detail.code === 'recipe_version_conflict' &&
			typeof detail.current_version === 'number' &&
			typeof detail.expected_version === 'number' &&
			detail.current !== null &&
			typeof detail.current === 'object'
		);
	}

	async function saveWithVersion(version: number) {
		if (!form || saving) return;
		saving = true;
		error = null;
		try {
			const saved = await api.updateRecipe(recipeId, form, version);
			baseVersion = saved.version;
			conflict = null;
			allowNavigation = true;
			const params = new URLSearchParams({ saved: 'updated' });
			if (returnTo) params.set('returnTo', returnTo);
			if (replacedTimeNotices(saved).length) params.set('timenotice', '1');
			await goto(`/recipes/${recipeId}?${params}`);
		} catch (err) {
			if (err instanceof ApiError && err.status === 409 && isConflictDetail(err.detail)) {
				conflict = {
					...err.detail,
					changes: openedRecipe
						? changedRecipeFields(openedRecipe, err.detail.current)
						: {}
				};
			} else if (err instanceof ApiError && err.status === 404) {
				conflict = null;
				error = 'Dieses Rezept wurde inzwischen gelöscht. Deine Eingaben bleiben erhalten.';
			} else {
				error = err instanceof ApiError ? err.message : 'Rezept konnte nicht gespeichert werden.';
			}
		} finally {
			saving = false;
		}
	}

	let fields = $state<ReturnType<typeof RecipeFieldsForm>>();

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (!form || baseVersion === null || saving) return;
		if (!fields?.validate()) return;
		if (!form.category_id) {
			error = 'Bitte wähle eine Kategorie aus.';
			return;
		}
		await saveWithVersion(baseVersion);
	}

	async function overwriteAfterConfirmation() {
		if (!conflict) return;
		const expectedVersion = conflict.current_version;
		showOverwriteConfirm = false;
		// Never skip the version check: a third editor may have saved meanwhile.
		await saveWithVersion(expectedVersion);
	}

	function leaveAfterConflict() {
		// The unsaved-changes guard in beforeNavigate asks for confirmation.
		conflict = null;
		void goto(detailHref);
	}

	// Own image changes bump the recipe version. Only advance the save base if nobody else
	// saved in between; otherwise the next save reports the normal conflict.
	api.setRecipeVersionListener((before, after) => {
		if (before === baseVersion) baseVersion = after;
	});
	onDestroy(() => api.setRecipeVersionListener(null));

	async function handleDelete() {
		deleting = true;
		try {
			await api.deleteRecipe(recipeId);
			allowNavigation = true;
			const params = new URLSearchParams({ deleted: '1' });
			if (originalCategoryId !== null) params.set('category', String(originalCategoryId));
			await goto(`/?${params}`);
		} catch {
			error = 'Rezept konnte nicht gelöscht werden.';
			deleting = false;
			showDeleteConfirm = false;
		}
	}
</script>

<svelte:head>
	<title>Rezept bearbeiten &middot; {cookbook.settings.cookbook_name}</title>
</svelte:head>

<PageToolbar backHref={detailHref} backLabel="Zurück zum Rezept" />

<div class="page-intro">
	<h1>Rezept bearbeiten</h1>
	{#if justCreated}
		<p class="alert alert-success">Rezept gespeichert!</p>
	{/if}
</div>

{#if error}
	<p class="alert alert-error" role="alert">{error}</p>
{/if}

{#if loading}
	<div class="skeleton" style="height: 400px;"></div>
{:else if form && baseVersion !== null}
	<RecipeImageManager {recipeId} version={baseVersion} bind:images highlight={justCreated} />

	<form onsubmit={handleSubmit}>
		<RecipeFieldsForm bind:this={fields} bind:form {categories} />

		<div class="form-actions">
			<a class="btn btn-secondary" href={detailHref}>Abbrechen</a>
			<button class="btn btn-primary" type="submit" aria-disabled={saving}>
				{saving ? 'Speichert …' : 'Änderungen speichern'}
			</button>
		</div>
	</form>

	{#if conflict && !showOverwriteConfirm}
		<RecipeConflictDialog
			{conflict}
			draft={form}
			{categories}
			busy={saving}
			oncontinue={() => (conflict = null)}
			onleave={leaveAfterConflict}
			onoverwrite={() => (showOverwriteConfirm = true)}
		/>
	{/if}
	{#if conflict && showOverwriteConfirm}
		<Modal title="Neueren Rezeptstand überschreiben?" onclose={() => (showOverwriteConfirm = false)}>
			<p>
				Du ersetzt damit ausdrücklich die aktuelle Version {conflict.current_version} durch
				deinen Entwurf. Änderungen anderer Personen können verloren gehen.
			</p>
			<p>Eine zwischenzeitlich erneut geänderte oder gelöschte Version wird weiterhin blockiert.</p>
			<div class="modal-actions">
				<button type="button" class="btn btn-secondary" onclick={() => (showOverwriteConfirm = false)}
					>Zurück zum Vergleich</button
				>
				<button type="button" class="btn btn-danger" onclick={overwriteAfterConfirmation} disabled={saving}
					>{saving ? 'Prüft …' : 'Ja, trotzdem überschreiben'}</button
				>
			</div>
		</Modal>
	{/if}

	<p class="delete-line">
		<button class="link-button" onclick={() => (showDeleteConfirm = true)}>Rezept löschen</button>
	</p>

	{#if showDeleteConfirm}
		<Modal
			title={`Rezept „${form.title}“ endgültig löschen?`}
			onclose={() => (showDeleteConfirm = false)}
		>
			<p class="muted">
				Dieses Rezept einschließlich aller Bilder, Kommentare, Bewertungen und Favoriten wird unwiderruflich gelöscht. Es gibt keinen Papierkorb und keine Wiederherstellung.
			</p>
			<div class="modal-actions">
				<!-- svelte-ignore a11y_autofocus -->
				<button class="btn btn-secondary" autofocus onclick={() => (showDeleteConfirm = false)}>
					Abbrechen
				</button>
				<button class="btn btn-danger" onclick={handleDelete} disabled={deleting}>
					{deleting ? 'Löscht …' : 'Rezept löschen'}
				</button>
			</div>
		</Modal>
	{/if}
{/if}

<style>
	.page-intro {
		margin-bottom: 1.5rem;
	}

	.delete-line {
		margin: 2rem 0 0;
		text-align: right;
	}
</style>
