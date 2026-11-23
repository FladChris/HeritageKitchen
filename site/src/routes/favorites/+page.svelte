<script lang="ts">
	import { offline } from '$lib/stores/offline.svelte';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import * as api from '$lib/api';
	import Icon from '$lib/components/Icon.svelte';
	import RecipeCard from '$lib/components/RecipeCard.svelte';
	import RecipeViewToggle from '$lib/components/RecipeViewToggle.svelte';
	import { auth } from '$lib/stores/auth.svelte';
	import { cookbook } from '$lib/stores/settings.svelte';
	import type { Favorite, FavoritePreferences, FavoriteSort, Recipe } from '$lib/types';

	const BATCH_SIZE = 20;
	const SORT_OPTIONS: { value: FavoriteSort; label: string }[] = [
		{ value: 'recent', label: 'Zuletzt favorisiert zuerst' },
		{ value: 'name', label: 'A–Z' },
		{ value: 'manual', label: 'Eigene Sortierung' }
	];

	type Account = { id: number };
	type Selection = {
		favorites: Favorite[];
		recipes: Partial<Record<number, Recipe>>;
		loadedCount: number;
	};

	let account: Account | null = null;
	let selection = $state<Selection>({ favorites: [], recipes: {}, loadedCount: 0 });
	let preferences = $state<FavoritePreferences>({ sort: 'recent', recipe_view: 'list' });
	let draft = $state<Favorite[] | null>(null);
	let loading = $state(true);
	let ready = $state(false);
	let saving = $state(false);
	let error = $state<string | null>(null);
	let busy = $derived(loading || saving);
	let visible = $derived(
		((offline.offline ? null : draft) ?? selection.favorites).flatMap((favorite) => {
			const recipe = selection.recipes[favorite.recipe_id];
			return recipe ? [{ favorite, recipe }] : [];
		})
	);

	onMount(() => {
		void auth.init();
	});

	$effect(() => {
		if (!auth.initialized) return;
		void offline.generation;
		const id = auth.user?.id;
		account = id === undefined ? null : { id };
		selection = { favorites: [], recipes: {}, loadedCount: 0 };
		preferences = { sort: 'recent', recipe_view: 'list' };
		draft = null;
		error = null;
		ready = false;
		saving = false;
		if (account) void load(account);
		else void goto('/login');
		return () => {
			account = null;
		};
	});

	function isCurrent(owner: Account) {
		return owner === account && auth.user?.id === owner.id;
	}

	function handleRequestError(owner: Account, cause: unknown, message: string) {
		if (!isCurrent(owner)) return;
		if (cause instanceof api.ApiError && (cause.status === 401 || cause.status === 403)) {
			ready = false;
			selection = { favorites: [], recipes: {}, loadedCount: 0 };
			draft = null;
			void auth.refresh();
			return;
		}
		error = message;
	}

	async function fetchRecipes(favorites: Favorite[]): Promise<Selection['recipes']> {
		const recipes = await Promise.all(
			favorites.map(async (favorite) => {
				try {
					const recipe = await api.getRecipe(favorite.recipe_id);
					return [favorite.recipe_id, recipe] as const;
				} catch (err) {
					if (err instanceof api.ApiError && err.status === 404) return null;
					throw err;
				}
			})
		);
		return Object.fromEntries(recipes.filter((entry) => entry !== null));
	}

	async function fetchSelection(owner: Account, sort: FavoriteSort): Promise<Selection> {
		const favorites = await api.listFavorites(sort, owner.id);
		const firstBatch = favorites.slice(0, BATCH_SIZE);
		return {
			favorites,
			recipes: await fetchRecipes(firstBatch),
			loadedCount: firstBatch.length
		};
	}

	async function load(owner: Account) {
		loading = true;
		error = null;
		try {
			const savedPreferences = await api.getFavoritePreferences(owner.id);
			if (!isCurrent(owner)) return;
			const next = await fetchSelection(owner, savedPreferences.sort);
			if (!isCurrent(owner)) return;
			preferences = savedPreferences;
			selection = next;
			ready = true;
		} catch (err) {
			handleRequestError(owner, err, 'Favoriten konnten nicht geladen werden.');
		} finally {
			if (isCurrent(owner)) loading = false;
		}
	}

	async function loadMore() {
		const owner = account;
		if (!owner || busy || selection.loadedCount >= selection.favorites.length) return;
		loading = true;
		error = null;
		const batch = selection.favorites.slice(
			selection.loadedCount,
			selection.loadedCount + BATCH_SIZE
		);
		try {
			const recipes = await fetchRecipes(batch);
			if (!isCurrent(owner)) return;
			selection.recipes = { ...selection.recipes, ...recipes };
			selection.loadedCount += batch.length;
		} catch (err) {
			handleRequestError(owner, err, 'Favoriten konnten nicht geladen werden. Versuch es erneut.');
		} finally {
			if (isCurrent(owner)) loading = false;
		}
	}

	async function setSort(sort: FavoriteSort) {
		const owner = account;
		if (!owner || busy || sort === preferences.sort) return;
		saving = true;
		error = null;
		try {
			const next = await fetchSelection(owner, sort);
			if (!isCurrent(owner)) return;
			await api.updateFavoritePreferences(owner.id, { sort });
			if (!isCurrent(owner)) return;
			preferences.sort = sort;
			selection = next;
		} catch (err) {
			handleRequestError(owner, err, 'Die Sortierung konnte nicht geändert werden.');
		} finally {
			if (isCurrent(owner)) saving = false;
		}
	}

	async function setRecipeView(view: FavoritePreferences['recipe_view']) {
		const owner = account;
		if (!owner || busy || view === preferences.recipe_view) return;
		saving = true;
		error = null;
		try {
			await api.updateFavoritePreferences(owner.id, { recipe_view: view });
			if (isCurrent(owner)) preferences.recipe_view = view;
		} catch (err) {
			handleRequestError(owner, err, 'Die Ansicht konnte nicht gespeichert werden.');
		} finally {
			if (isCurrent(owner)) saving = false;
		}
	}

	function moveFavorite(index: number, direction: -1 | 1) {
		const target = visible[index + direction];
		if (!draft || busy || !target) return;
		const from = draft.findIndex((favorite) => favorite.id === visible[index].favorite.id);
		const to = draft.findIndex((favorite) => favorite.id === target.favorite.id);
		[draft[from], draft[to]] = [draft[to], draft[from]];
	}

	async function saveOrder() {
		const owner = account;
		if (!owner || busy || !draft) return;
		saving = true;
		error = null;
		try {
			const favorites = await api.setFavoriteOrder(owner.id, draft.map((favorite) => favorite.id));
			if (!isCurrent(owner)) return;
			selection.favorites = favorites;
			draft = null;
		} catch (err) {
			if (!isCurrent(owner)) return;
			if (err instanceof api.ApiError && err.status === 409) {
				draft = null;
				await load(owner);
				if (isCurrent(owner) && !error)
					error = 'Deine Favoriten haben sich geändert. Prüfe die aktuelle Reihenfolge.';
			} else {
				handleRequestError(owner, err, 'Die Reihenfolge konnte nicht gespeichert werden. Versuch es erneut.');
			}
		} finally {
			if (isCurrent(owner)) saving = false;
		}
	}
</script>

<svelte:head>
	<title>Favoriten &middot; {cookbook.settings.cookbook_name}</title>
</svelte:head>

<div class="page-header">
	<h1>Meine Favoriten</h1>
	{#if ready && selection.favorites.length > 0 && !draft && !offline.offline}
		<RecipeViewToggle view={preferences.recipe_view} disabled={busy} onchange={setRecipeView} />
	{/if}
</div>

{#if ready && selection.favorites.length > 0 && !offline.offline}
	<div class="favorite-tools">
		{#if draft}
			<button class="btn btn-primary btn-sm" onclick={saveOrder} disabled={busy}>
				Reihenfolge speichern
			</button>
			<button class="btn btn-secondary btn-sm" onclick={() => (draft = null)} disabled={busy}>
				Abbrechen
			</button>
		{:else}
			<div class="sort-switch" role="group" aria-label="Favoriten sortieren">
				{#each SORT_OPTIONS as option (option.value)}
					<button
						class="btn btn-quiet btn-sm"
						aria-pressed={preferences.sort === option.value}
						disabled={busy}
						onclick={() => setSort(option.value)}>{option.label}</button
					>
				{/each}
			</div>
			{#if preferences.sort === 'manual' && selection.favorites.length > 1}
				<button
					class="btn btn-quiet btn-sm"
					disabled={busy}
					onclick={() => (draft = [...selection.favorites])}
					><Icon name="reorder" /> Reihenfolge ändern</button
				>
			{/if}
		{/if}
	</div>
{/if}

{#if error}
	<p class="alert alert-error" role="alert">{error}</p>
	{#if !ready}
		<button class="btn btn-secondary" onclick={() => account && load(account)}>Erneut laden</button>
	{/if}
{/if}

{#if loading && visible.length === 0}
	<div class="recipe-grid" class:list={preferences.recipe_view === 'list'} aria-hidden="true">
		{#each Array(3) as _, i (i)}
			<div class="skeleton" class:skeleton-row={preferences.recipe_view === 'list'}></div>
		{/each}
	</div>
{:else if ready && visible.length === 0 && selection.loadedCount === selection.favorites.length}
	<div class="empty-state">
		<p>Du hast noch keine Favoriten gespeichert.</p>
		<p class="muted">Klicke bei einem Rezept auf den Stern, um es hier zu sammeln.</p>
		<p><a class="btn btn-secondary" href="/">Rezepte entdecken</a></p>
	</div>
{:else if draft && !offline.offline}
	<ol class="order-list" aria-label="Eigene Favoritenreihenfolge">
		{#each visible as { favorite, recipe }, index (favorite.id)}
			{@const origin = recipe.origin_person?.trim()}
			{@const label = origin ? recipe.title + ' · ' + origin : recipe.title}
			<li>
				<span>{label}</span>
				<button
					class="icon-btn"
					aria-label={label + ' nach oben'}
					title="Nach oben"
					disabled={busy || index === 0}
					onclick={() => moveFavorite(index, -1)}><Icon name="up" /></button
				>
				<button
					class="icon-btn"
					aria-label={label + ' nach unten'}
					title="Nach unten"
					disabled={busy || index === visible.length - 1}
					onclick={() => moveFavorite(index, 1)}><Icon name="down" /></button
				>
			</li>
		{/each}
	</ol>
{:else if ready}
	<div class="recipe-grid" class:list={preferences.recipe_view === 'list'}>
		{#each visible as { favorite, recipe } (favorite.id)}
			<RecipeCard {recipe} layout={preferences.recipe_view} overview="/favorites" />
		{/each}
	</div>
{/if}

{#if selection.loadedCount < selection.favorites.length}
	<div class="load-more">
		<button class="btn btn-secondary" onclick={loadMore} disabled={busy}
			>{loading ? 'Lädt …' : 'Weitere Rezepte laden'}</button
		>
	</div>
{/if}

<style>
	.page-header {
		max-width: var(--measure);
	}

	.favorite-tools,
	.sort-switch {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
	.favorite-tools {
		margin-bottom: 1rem;
	}
	.sort-switch button {
		min-height: 44px;
	}
	.sort-switch button[aria-pressed='true'] {
		color: var(--color-text);
		text-decoration: underline 2px var(--color-primary);
		text-underline-offset: 0.45em;
	}
	.order-list {
		list-style: none;
		padding: 0;
	}
	.order-list li {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding-block: 0.25rem;
		border-bottom: 1px solid var(--color-border);
	}
	.order-list span {
		flex: 1;
		min-width: 0;
		overflow-wrap: anywhere;
	}
	.skeleton {
		aspect-ratio: 4 / 3;
	}
	.skeleton-row {
		aspect-ratio: auto;
		height: 64px;
		margin-bottom: 0.5rem;
	}
	.load-more {
		margin-top: 1.5rem;
	}
</style>
