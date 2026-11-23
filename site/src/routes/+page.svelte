<script lang="ts">
	import { offline } from '$lib/stores/offline.svelte';
	import { cookbook } from '$lib/stores/settings.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import * as api from '$lib/api';
	import { ApiError } from '$lib/api';
	import type {
		Category,
		OtherCategoryHit,
		RecipeSummary,
		ViewPreferences,
		ViewPreferencesUpdate
	} from '$lib/types';
	import OrderList from '$lib/components/OrderList.svelte';
	import RecipeCard from '$lib/components/RecipeCard.svelte';
	import RecipeViewToggle from '$lib/components/RecipeViewToggle.svelte';
	import CategoryTile from '$lib/components/CategoryTile.svelte';
	import CategoryHeader from '$lib/components/CategoryHeader.svelte';
	import CategoryCreateDialog from '$lib/components/CategoryCreateDialog.svelte';
	import { auth } from '$lib/stores/auth.svelte';

	const PAGE_SIZE = 20;
	const VIEW_STORAGE_KEY = 'heritagekitchen:recipe-view';
	type CategorySort = ViewPreferences['category_sort'];
	let categorySort = $state<CategorySort>('name');
	const SORT_OPTIONS: { value: CategorySort; label: string }[] = [
		{ value: 'name', label: 'A–Z' },
		{ value: 'count', label: 'Meiste Rezepte' },
		{ value: 'manual', label: 'Eigene' }
	];
	let reordering = $state(false);
	let recipeSort = $state<'title' | 'manual'>('title');
	let recipeReordering = $state(false);
	let recipeOrderItems = $state<{ id: number; name: string }[]>([]);
	let recipeOrderBusy = $state(false);
	let recipeOrderError = $state('');
	const categoryCollator = new Intl.Collator('de', { sensitivity: 'base', numeric: true });
	let recent = $state<RecipeSummary[]>([]);
	let recentError = $state(false);

	let recipes = $state<RecipeSummary[]>([]);
	let recipeTotal = $state(0);
	let otherCategoryHits = $state<OtherCategoryHit[]>([]);
	let recipePage = $state(1);
	let mounted = $state(false);
	let requestId = 0;
	let categoryRequest = 0;
	let recentRequest = 0;
	let categories = $state<Category[]>([]);
	let personalOrder = $state<number[]>([]);
	let preferencesReady = $state(false);
	let preferencesBusy = $state(false);
	let preferencesError = $state('');
	let pendingPreferences: ViewPreferencesUpdate = {};
	let preferenceRequest = 0;
	const preferencesDisabled = $derived(!preferencesReady || preferencesBusy);
	const manualCategories = $derived.by(() => {
		const positions = new Map(personalOrder.map((id, index) => [id, index]));
		return [...categories].sort(
			(a, b) => (positions.get(a.id) ?? positions.size) - (positions.get(b.id) ?? positions.size)
		);
	});
	const sortedCategories = $derived.by(() => {
		if (categorySort === 'manual' && auth.isLoggedIn) return manualCategories;
		return [...categories].sort((a, b) => {
			const countDifference =
				categorySort === 'count' ? (b.recipe_count ?? 0) - (a.recipe_count ?? 0) : 0;
			return countDifference || categoryCollator.compare(a.name, b.name) || a.id - b.id;
		});
	});
	let searchInput = $state('');
	let activeSearch = $state('');
	let loading = $state(true);
	let error = $state<string | null>(null);
	let searchTimeout: ReturnType<typeof setTimeout>;
	let recipeView = $state<'grid' | 'list'>('list');

	let categoryError = $state<string | null>(null);
	let showCreateCategory = $state(false);

	const categoryParam = $derived(page.url.searchParams.get('category'));
	const searchParam = $derived(page.url.searchParams.get('search'));
	$effect(() => {
		if (searchParam) {
			searchInput = searchParam;
			activeSearch = searchParam.trim();
		}
	});
	const selectedCategoryId = $derived(categoryParam ? Number(categoryParam) : null);
	const overview = $derived.by(() => {
		const params = new URLSearchParams();
		if (selectedCategoryId) params.set('category', String(selectedCategoryId));
		if (activeSearch) params.set('search', activeSearch);
		return params.size ? `/?${params}` : '/';
	});
	const selectedCategory = $derived(
		selectedCategoryId ? (categories.find((c) => c.id === selectedCategoryId) ?? null) : null
	);
	// Browsing mode: category tiles, unless the person picked a category or is searching.
	const browsingCategories = $derived(!selectedCategoryId && !activeSearch);

	const effectiveRecipeSort = $derived(auth.isLoggedIn ? recipeSort : 'title');

	$effect(() => {
		void offline.generation;
		if (mounted) void loadRecipes(selectedCategoryId, activeSearch, effectiveRecipeSort);
	});

	$effect(() => {
		if (mounted && offline.generation) {
			void loadRecent();
			void loadCategories();
		}
	});

	$effect(() => {
		void [selectedCategoryId, auth.user?.id];
		recipeSort = 'title';
		recipeReordering = false;
		recipeOrderError = '';
	});

	$effect(() => {
		if (auth.initialized) void loadViewPreferences(auth.user?.id);
	});

	async function loadRecipes(categoryId: number | null, search: string, sort: 'title' | 'manual') {
		const currentRequest = ++requestId;
		recipes = [];
		recipeTotal = 0;
		otherCategoryHits = [];
		recipePage = 1;
		error = null;
		if (!categoryId && !search) {
			loading = false;
			return;
		}
		loading = true;
		try {
			const result = await api.listRecipes({
				search: search || undefined,
				category_id: categoryId ?? undefined,
				sort: sort === 'manual' ? sort : undefined,
				page: 1,
				page_size: PAGE_SIZE
			});
			if (currentRequest === requestId) {
				recipes = result.items;
				recipeTotal = result.total;
				otherCategoryHits = result.other_categories ?? [];
			}
		} catch {
			if (currentRequest === requestId) error = 'Rezepte konnten nicht geladen werden.';
		} finally {
			if (currentRequest === requestId) loading = false;
		}
	}

	async function loadMoreRecipes() {
		if (loading || recipes.length >= recipeTotal) return;
		const currentRequest = requestId;
		loading = true;
		error = null;
		try {
			const nextPage = recipePage + 1;
			const result = await api.listRecipes({
				search: activeSearch || undefined,
				category_id: selectedCategoryId ?? undefined,
				sort: effectiveRecipeSort === 'manual' ? 'manual' : undefined,
				page: nextPage,
				page_size: PAGE_SIZE
			});
			if (currentRequest === requestId) {
				// A recipe added or removed in the meantime shifts the pages, so skip known entries.
				const knownIds = new Set(recipes.map((recipe) => recipe.id));
				recipes = [...recipes, ...result.items.filter((recipe) => !knownIds.has(recipe.id))];
				recipeTotal = result.items.length === 0 ? recipes.length : result.total;
				recipePage = nextPage;
			}
		} catch {
			if (currentRequest === requestId) error = 'Weitere Rezepte konnten nicht geladen werden.';
		} finally {
			if (currentRequest === requestId) loading = false;
		}
	}

	function handleSearchInput() {
		clearTimeout(searchTimeout);
		searchTimeout = setTimeout(() => {
			activeSearch = searchInput.trim();
		}, 300);
	}

	async function loadCategories() {
		const request = ++categoryRequest;
		try {
			const result = await api.listCategories();
			if (request === categoryRequest) categories = result;
		} catch {
			if (request === categoryRequest)
				categoryError = 'Kategorien konnten nicht geladen werden. Lade die Seite erneut.';
		}
	}

	async function handleCategoryDeleted() {
		goto('/');
		await loadCategories();
	}

	async function handleCategoryCreated() {
		await loadCategories();
		showCreateCategory = false;
	}

	async function loadViewPreferences(userId: number | undefined) {
		const request = ++preferenceRequest;
		preferencesReady = false;
		preferencesBusy = false;
		preferencesError = '';
		pendingPreferences = {};
		categorySort = 'name';
		recipeView = 'list';
		personalOrder = [];
		cancelCategoryOrder();

		if (userId === undefined) {
			try {
				const view = localStorage.getItem(VIEW_STORAGE_KEY);
				if (view === 'grid' || view === 'list') recipeView = view;
			} catch {
				// Guest preferences are optional.
			}
			preferencesReady = true;
			return;
		}
		try {
			const preferences = await api.getViewPreferences(userId);
			if (request !== preferenceRequest || auth.user?.id !== userId) return;
			categorySort = preferences.category_sort;
			recipeView = preferences.recipe_view;
			personalOrder = preferences.category_ids;
			preferencesReady = true;
		} catch {
			if (request === preferenceRequest && auth.user?.id === userId)
				preferencesError = 'Deine Ansicht konnte nicht geladen werden.';
		}
	}

	async function saveViewPreferences(update: ViewPreferencesUpdate = {}) {
		const userId = auth.user?.id;
		if (userId === undefined || preferencesDisabled) return;
		const request = preferenceRequest;
		pendingPreferences = { ...pendingPreferences, ...update };
		preferencesBusy = true;
		preferencesError = '';
		try {
			await api.updateViewPreferences(userId, pendingPreferences);
			if (request === preferenceRequest) pendingPreferences = {};
		} catch {
			if (request === preferenceRequest)
				preferencesError = 'Deine Ansicht konnte nicht gespeichert werden.';
		} finally {
			if (request === preferenceRequest) preferencesBusy = false;
		}
	}

	function retryViewPreferences() {
		if (preferencesReady) void saveViewPreferences();
		else void loadViewPreferences(auth.user?.id);
	}

	function setRecipeView(view: 'grid' | 'list') {
		recipeView = view;
		if (auth.isLoggedIn) {
			void saveViewPreferences({ recipe_view: view });
			return;
		}
		try {
			localStorage.setItem(VIEW_STORAGE_KEY, view);
		} catch {
			// Best-effort per-browser convenience only.
		}
	}

	function setCategorySort(sort: CategorySort) {
		categorySort = sort;
		if (auth.isLoggedIn) {
			void saveViewPreferences({ category_sort: sort });
		}
	}

	function startCategoryOrder() {
		reordering = true;
	}

	function cancelCategoryOrder() {
		reordering = false;
	}

	function savePersonalOrder(categoryIds: number[]) {
		personalOrder = categoryIds;
		categorySort = 'manual';
		void saveViewPreferences({
			category_order: { category_ids: categoryIds },
			category_sort: 'manual'
		});
	}

	async function startRecipeOrder() {
		if (!selectedCategoryId) return;
		recipeOrderBusy = true;
		recipeOrderError = '';
		try {
			// Saving needs every recipe of the category, not only the loaded page.
			const all: RecipeSummary[] = [];
			for (let pageNumber = 1; ; pageNumber++) {
				const result = await api.listRecipes({
					sort: 'manual',
					category_id: selectedCategoryId,
					page: pageNumber,
					page_size: 100
				});
				all.push(...result.items);
				if (result.items.length === 0 || all.length >= result.total) break;
			}
			recipeOrderItems = all.map((recipe) => ({ id: recipe.id, name: recipe.title }));
			recipeReordering = true;
		} catch {
			recipeOrderError = 'Die Rezepte konnten nicht geladen werden.';
		} finally {
			recipeOrderBusy = false;
		}
	}

	let recipeOrderSaving = false;
	let latestRecipeOrder: number[] | null = null;

	// Only one request is in flight; moves made meanwhile are sent afterwards, latest order last.
	async function saveRecipeOrder(recipeIds: number[]) {
		latestRecipeOrder = recipeIds;
		if (recipeOrderSaving || !selectedCategoryId) return;
		recipeOrderSaving = true;
		recipeOrderError = '';
		try {
			while (latestRecipeOrder) {
				const next = latestRecipeOrder;
				latestRecipeOrder = null;
				try {
					await api.saveRecipeOrder(selectedCategoryId, next);
				} catch (err) {
					latestRecipeOrder = null;
					recipeOrderError =
						err instanceof ApiError && err.status === 409
							? 'Die Rezepte haben sich geändert. Lade die Seite neu.'
							: 'Deine Reihenfolge konnte nicht gespeichert werden.';
				}
			}
		} finally {
			recipeOrderSaving = false;
		}
	}

	function finishRecipeOrder() {
		recipeReordering = false;
		void loadRecipes(selectedCategoryId, activeSearch, effectiveRecipeSort);
	}

	async function loadRecent() {
		const request = ++recentRequest;
		try {
			const result = await api.listRecipes({ sort: 'newest', page_size: 3 });
			if (request !== recentRequest) return;
			recent = result.items;
			recentError = false;
		} catch {
			if (request === recentRequest) recentError = true;
		}
	}

	onMount(async () => {
		await auth.init();
		void loadRecent();
		await loadCategories();
		mounted = true;
	});
</script>

<svelte:head>
	<title>{cookbook.settings.cookbook_name}</title>
</svelte:head>

<div class="index" class:wide={!browsingCategories && recipeView === 'grid'}>
	{#if page.url.searchParams.get('deleted') === '1'}
		<p class="alert alert-success" role="status">Rezept gelöscht.</p>
	{/if}
	{#if selectedCategory}
		<CategoryHeader
			category={selectedCategory}
			bind:error={categoryError}
			onchanged={loadCategories}
			ondeleted={handleCategoryDeleted}
		/>
	{:else}
		<div class="page-intro">
			<h1 class="display">{cookbook.settings.home_title}</h1>
			<p class="lede">{cookbook.settings.home_tagline}</p>
		</div>
	{/if}

	<div class="controls" class:category-controls={!!selectedCategory}>
		<div class="field search-field">
			<label for="search">Suche</label>
			<input
				id="search"
				type="search"
				placeholder="Rezepte durchsuchen …"
				bind:value={searchInput}
				oninput={handleSearchInput}
			/>
		</div>
		{#if !browsingCategories && (loading || recipes.length > 0)}
			<RecipeViewToggle view={recipeView} disabled={preferencesDisabled} onchange={setRecipeView} />
		{/if}
	</div>

	{#if preferencesError}
		<div class="alert alert-error" role="alert">
			{preferencesError}
			<button class="btn btn-secondary btn-sm" onclick={retryViewPreferences}
				>Erneut versuchen</button
			>
		</div>
	{/if}

	{#if error}
		<p class="alert alert-error">{error}</p>
	{/if}

	{#if recipeOrderError}
		<p class="alert alert-error" role="alert">{recipeOrderError}</p>
	{/if}

	{#if selectedCategory && !browsingCategories && recipeTotal > 1}
		{#if recipeReordering}
			<div class="category-bar reorder-bar">
				<p>
					Ziehe die Rezepte am Griff oder nutze die Pfeile. Deine Reihenfolge wird automatisch
					gespeichert.
				</p>
				<div class="bar-actions">
					<button class="btn btn-secondary btn-sm" onclick={finishRecipeOrder}>Fertig</button>
				</div>
			</div>
		{:else}
			<div class="category-bar category-tools">
				<div class="sort-switch" role="group" aria-label="Rezepte sortieren">
					<span class="sort-label" aria-hidden="true">Sortieren</span>
					<button aria-pressed={effectiveRecipeSort === 'title'} onclick={() => (recipeSort = 'title')}
						>A–Z</button
					>
					{#if auth.isLoggedIn}
						<button
							aria-pressed={effectiveRecipeSort === 'manual'}
							onclick={() => (recipeSort = 'manual')}>Eigene</button
						>
					{/if}
				</div>
				{#if auth.isLoggedIn && !offline.offline && effectiveRecipeSort === 'manual' && !activeSearch}
					<div class="bar-actions">
						<button class="btn btn-quiet btn-sm" disabled={recipeOrderBusy} onclick={startRecipeOrder}
							><Icon name="reorder" /> Reihenfolge ändern</button
						>
					</div>
				{/if}
			</div>
		{/if}
	{/if}

	{#if loading && recipes.length === 0}
		<div class="recipe-grid" class:list={recipeView === 'list'} aria-hidden="true">
			{#each Array(4) as _, i (i)}
				<div class="skeleton" class:skeleton-row={recipeView === 'list'}></div>
			{/each}
		</div>
	{:else if browsingCategories}
		<div class="overview">
			<div class="categories">
				{#if categoryError}
					<p class="alert alert-error" role="alert">{categoryError}</p>
				{/if}
				{#if reordering}
					<div class="category-bar reorder-bar">
						<p>
							Ziehe die Kategorien am Griff oder nutze die Pfeile.
							Deine Reihenfolge wird automatisch gespeichert.
						</p>
						<div class="bar-actions">
							<button class="btn btn-secondary btn-sm" onclick={cancelCategoryOrder}>Fertig</button>
						</div>
					</div>
				{:else if categories.length > 1 || auth.hasRole('admin')}
					<div class="category-bar category-tools" role="group" aria-label="Kategorien">
						{#if categories.length > 1}
							<div class="sort-switch" role="group" aria-label="Kategorien sortieren">
								<span class="sort-label" aria-hidden="true">Sortieren</span>
								{#each SORT_OPTIONS as option (option.value)}
									{#if option.value !== 'manual' || auth.isLoggedIn}
										<button
											aria-pressed={categorySort === option.value}
											disabled={preferencesDisabled}
											onclick={() => setCategorySort(option.value)}>{option.label}</button
										>
									{/if}
								{/each}
							</div>
						{/if}
						{#if auth.isLoggedIn && !offline.offline}
							<div class="bar-actions" role="group" aria-label="Kategorieaktionen">
								{#if categories.length > 1}
									<button
										class="btn btn-quiet btn-sm"
										disabled={preferencesDisabled}
										onclick={startCategoryOrder}
										><Icon name="reorder" /> Reihenfolge ändern</button
									>
								{/if}
								{#if auth.hasRole('admin')}
									<button class="btn btn-quiet btn-sm" onclick={() => (showCreateCategory = true)}
										><Icon name="plus" /> Kategorie hinzufügen</button
									>
								{/if}
							</div>
						{/if}
					</div>
				{/if}
				{#if categories.length === 0}
					<div class="empty-state">
						<p>Noch keine Kategorien angelegt.</p>
						{#if auth.hasRole('admin')}<p class="muted">
								Leg eine Kategorie an, um deine Rezepte zu ordnen.
							</p>{/if}
					</div>
				{:else}
					{#if reordering}
						<OrderList
							items={manualCategories.map((category) => ({
								id: category.id,
								name: category.name,
								count: category.recipe_count ?? 0
							}))}
							disabled={preferencesDisabled}
							onchange={savePersonalOrder}
						/>
					{:else}
						<div class="category-list">
							{#each sortedCategories as category (category.id)}
								<CategoryTile {category} count={category.recipe_count ?? 0} />
							{/each}
						</div>
					{/if}
				{/if}
			</div>
			<section class="recent" aria-labelledby="recent-title">
				<h2 id="recent-title">Zuletzt eingetragen</h2>
				{#if recentError}<p role="status">
						Die neuesten Rezepte konnten nicht geladen werden.
					</p>{:else if recent.length === 0}<p class="muted">Noch keine Rezepte eingetragen.</p>{/if}
				{#each recent as recipe (recipe.id)}<RecipeCard {recipe} {overview} layout="recent" />{/each}
			</section>
		</div>
	{:else if recipes.length === 0}
		{#if !error}
			<div class="empty-state">
				{#if activeSearch}<p>Keine Rezepte zu deiner Suche gefunden.</p>
					{#if otherCategoryHits.length > 0}
						<p class="muted">In anderen Kategorien gibt es passende Rezepte:</p>
						<ul class="other-categories">
							{#each otherCategoryHits as hit (hit.id)}
								<li><a href={`/?category=${hit.id}&search=${encodeURIComponent(activeSearch)}`}>{hit.name} – {hit.count} Treffer</a></li>
							{/each}
						</ul>
					{:else}<p class="muted">Versuch es mit einem anderen Suchbegriff.</p>{/if}{:else}<p>
						In dieser Kategorie gibt es noch keine Rezepte.
					</p>
					{#if auth.hasRole('editor')}<p>
							<a class="btn btn-secondary" href={`/recipes/new?category=${selectedCategoryId}`}
								>Rezept hinzufügen</a
							>
						</p>{/if}{/if}
			</div>
		{/if}
	{:else if recipeReordering}
		<OrderList items={recipeOrderItems} onchange={saveRecipeOrder} />
	{:else}
		<div class="recipe-grid" class:list={recipeView === 'list'}>
			{#each recipes as recipe (recipe.id)}
				<RecipeCard
					{recipe}
					{overview}
					layout={recipeView}
					showCategory={!selectedCategory || !!activeSearch}
				/>
			{/each}
		</div>
		{#if recipes.length < recipeTotal}
			<div class="load-more">
				<button class="btn btn-secondary" onclick={loadMoreRecipes} disabled={loading}>
					{loading ? 'Lädt …' : `Weitere Rezepte laden (${recipeTotal - recipes.length} übrig)`}
				</button>
			</div>
		{/if}
	{/if}
</div>

{#if showCreateCategory && auth.hasRole('admin')}
	<CategoryCreateDialog oncreated={handleCategoryCreated} onclose={() => (showCreateCategory = false)} />
{/if}

<style>
	.category-bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.25rem 1rem;
		border-bottom: 1px solid var(--color-border-subtle);
	}
	.category-tools {
		justify-content: flex-start;
		gap: 0 0.75rem;
	}
	.category-tools .bar-actions {
		gap: 0.25rem;
		margin-left: 0;
	}
	.sort-switch + .bar-actions {
		padding-left: 0.75rem;
		border-left: 1px solid var(--color-border-subtle);
	}
	.sort-switch {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.15rem;
		font-size: var(--text-sm);
	}
	.sort-label {
		color: var(--color-text-muted);
		margin-right: 0.35rem;
	}
	.sort-switch button {
		min-width: 44px;
		min-height: 44px;
		padding: 0 0.5rem;
		border: none;
		background: none;
		color: var(--color-text-muted);
		font-weight: 600;
	}
	.sort-switch button:hover {
		color: var(--color-text);
	}
	.sort-switch button[aria-pressed='true'] {
		color: var(--color-text);
		text-decoration: underline 2px var(--color-primary);
		text-underline-offset: 0.45em;
	}
	.bar-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-left: auto;
	}
	.reorder-bar {
		padding-block: 0.5rem;
	}
	.reorder-bar p {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.index {
		max-width: var(--measure);
	}
	.index:has(> .overview),
	.index.wide {
		max-width: none;
	}
	/* Toolbar and heading stay put when the view switches between list and grid. */
	.index.wide > :global(.page-toolbar),
	.index.wide > .page-intro {
		max-width: var(--measure);
	}
	.page-intro {
		margin-bottom: 1.5rem;
	}
	.page-intro h1 {
		margin-bottom: 0.5rem;
	}
	.lede {
		margin: 0;
		color: var(--color-text-muted);
	}
	.controls {
		display: flex;
		align-items: flex-end;
		gap: 0.75rem;
		max-width: var(--measure);
		margin-bottom: 1rem;
	}
	.controls .field {
		margin-bottom: 0;
		flex: 1;
		min-width: 0;
	}
	.overview {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 2.5rem;
	}
	.categories,
	.recent {
		max-width: var(--measure);
	}
	@media (min-width: 60rem) {
		.overview {
			grid-template-columns: minmax(0, 65fr) minmax(0, 35fr);
			gap: 1.5rem;
		}
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
		margin: 2rem 0;
	}
	@media (max-width: 600px) {
		.category-tools {
			flex-direction: column;
			align-items: flex-start;
		}
		.sort-switch + .bar-actions {
			padding-left: 0;
			border-left: 0;
			border-top: 1px solid var(--color-border-subtle);
		}
		.category-controls {
			margin-bottom: 0.5rem;
		}
	}
</style>
