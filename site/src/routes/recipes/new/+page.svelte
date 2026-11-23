<script lang="ts">
	import { cookbook } from '$lib/stores/settings.svelte';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { guardUnsavedChanges } from '$lib/unsaved-changes';
	import * as api from '$lib/api';
	import { ApiError } from '$lib/api';
	import { auth } from '$lib/stores/auth.svelte';
	import { replacedTimeNotices } from '$lib/recipe-times';
	import type { Category, RecipeInput } from '$lib/types';
	import RecipeFieldsForm from '$lib/components/RecipeFieldsForm.svelte';
	import PageToolbar from '$lib/components/PageToolbar.svelte';

	let categories = $state<Category[] | null>(null);
	let saving = $state(false);
	let error = $state<string | null>(null);

	const preselectedCategoryId = (() => {
		const raw = page.url.searchParams.get('category');
		const parsed = raw ? Number(raw) : null;
		return parsed && Number.isFinite(parsed) ? parsed : null;
	})();

	let form = $state<RecipeInput>({
		history: null,
		preparation_days: 1,
		day_titles: null,
		title: '',
		summary: null,
		preparation_time: null,
		cooking_time: null,
		cooking_time_max: null,
		rest_time: null,
		rest_time_max: null,
		servings: null,
		origin_person: null,
		notes: null,
		important_notes: null,
		category_id: preselectedCategoryId,
		ingredients: [],
		ingredient_groups: [],
		steps: []
	});

	let preselectedCategoryName = $state<string | null>(null);
	let originalForm = $state(JSON.stringify(form));
	let allowNavigation = false;
	const dirty = $derived(JSON.stringify(form) !== originalForm);

	guardUnsavedChanges(() => allowNavigation || !dirty);

	onMount(async () => {
		await auth.init();
		if (!auth.hasRole('editor')) {
			goto('/login');
			return;
		}
		try {
			categories = await api.listCategories();
			if (preselectedCategoryId) {
				preselectedCategoryName =
					categories.find((c) => c.id === preselectedCategoryId)?.name ?? null;
				if (!preselectedCategoryName) {
					form.category_id = null;
					// Normalize only the initial selection; never mark user edits as saved.
					const initial = JSON.parse(originalForm) as RecipeInput;
					initial.category_id = null;
					originalForm = JSON.stringify(initial);
				}
			}
		} catch {
			error = 'Kategorien konnten nicht geladen werden.';
		}
	});

	let fields = $state<ReturnType<typeof RecipeFieldsForm>>();

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (saving || !categories?.length) return;
		if (!fields?.validate()) return;
		error = null;
		if (!categories.some((category) => category.id === form.category_id)) {
			error = 'Bitte wähle eine Kategorie aus.';
			return;
		}
		saving = true;
		try {
			const created = await api.createRecipe(form);
			allowNavigation = true;
			const params = new URLSearchParams({ saved: 'created' });
			if (replacedTimeNotices(created).length) params.set('timenotice', '1');
			await goto(`/recipes/${created.id}?${params}`);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Rezept konnte nicht gespeichert werden.';
		} finally {
			saving = false;
		}
	}
</script>

<svelte:head>
	<title>Neues Rezept &middot; {cookbook.settings.cookbook_name}</title>
</svelte:head>

<PageToolbar
	backHref={preselectedCategoryId ? `/?category=${preselectedCategoryId}` : '/'}
	backLabel={preselectedCategoryName
		? `Zurück zu ${preselectedCategoryName}`
		: 'Zurück zu allen Rezepten'}
/>

<div class="page-intro">
	<h1>Neues Rezept{preselectedCategoryName ? ` in ${preselectedCategoryName}` : ''}</h1>
	<p class="muted">
		Titel und Kategorie reichen zum Speichern. Zutaten, Zubereitung, Bilder und weitere Details
		kannst du danach noch ergänzen.
	</p>
</div>

{#if error}
	<p class="alert alert-error" role="alert">{error}</p>
{/if}

<form onsubmit={handleSubmit}>
	<RecipeFieldsForm bind:this={fields} bind:form {categories} />

	<div class="form-actions">
		<a
			class="btn btn-secondary"
			href={preselectedCategoryId ? `/?category=${preselectedCategoryId}` : '/'}
		>
			Abbrechen
		</a>
		<button class="btn btn-primary" type="submit" disabled={saving || !categories?.length}>
			{saving ? 'Speichert …' : 'Rezept speichern'}
		</button>
	</div>
</form>

<style>
	.page-intro {
		max-width: var(--measure);
		margin-bottom: 1.5rem;
	}
</style>
