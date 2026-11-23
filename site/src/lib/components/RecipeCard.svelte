<script lang="ts">
	import { offlineImage } from '$lib/offline/installed';
	import type { RecipeSummary } from '$lib/types';
	import { coverImage } from '$lib/recipe-image';
	import { formatMinutes } from '$lib/format-time';
	import { summaryTimes } from '$lib/recipe-times';
	import Icon from './Icon.svelte';
	let {
		recipe,
		layout = 'list',
		showCategory = true,
		overview
	}: {
		recipe: RecipeSummary;
		layout?: 'grid' | 'list' | 'recent';
		showCategory?: boolean;
		overview?: string;
	} = $props();
	const cover = $derived(coverImage(recipe.images));
	const timeTotal = $derived(summaryTimes(recipe).total);
	const totalTime = $derived(timeTotal ? (timeTotal.to ?? timeTotal.from) : 0);
	const duration = $derived(
		recipe.preparation_days > 1
			? `${recipe.preparation_days} Tage`
			: totalTime > 0
				? formatMinutes(totalTime)
				: ''
	);
	const category = $derived(showCategory ? recipe.category?.name : undefined);
	const origin = $derived(recipe.origin_person?.trim());
	const recentMetadata = $derived([category, duration].filter(Boolean).join(' · '));
</script>

<a
	class="recipe-card"
	class:list={layout !== 'grid'}
	class:recent={layout === 'recent'}
	href={`/recipes/${recipe.id}${overview ? `?returnTo=${encodeURIComponent(overview)}` : ''}`}
>
	{#if cover}<img
			src={offlineImage(cover.file_path)}
			alt={cover.alt_text ?? ''}
			loading="lazy"
		/>{:else}<span class="photo-placeholder" aria-hidden="true">
			<Icon name="camera" />
		</span>{/if}
	<div class="recipe-card-body">
		<h3>{recipe.title}</h3>
		{#if layout === 'recent'}
			{#if origin}<p class="origin">{origin}</p>{/if}
			{#if recentMetadata}<p class="meta">{recentMetadata}</p>{/if}
		{:else}
			{#if recipe.origin_person}<p>von {recipe.origin_person}</p>{/if}
			<div class="meta">
				{#if category}<span>{category}</span>{/if}
				{#if duration}<span>{duration}</span>{/if}
			</div>
		{/if}
	</div>
</a>

<style>
	.recipe-card {
		display: flex;
		flex-direction: column;
		color: var(--color-text);
		border-bottom: 1px solid var(--color-border);
		padding: 0.5rem 0;
		gap: 0.8rem;
	}
	.recipe-card:hover {
		text-decoration: none;
		background: var(--color-surface-raised);
	}
	.recipe-card img,
	.photo-placeholder {
		display: block;
		width: 100%;
		aspect-ratio: 4 / 3;
		object-fit: cover;
		border: 1px solid var(--color-border-strong);
	}
	.recipe-card.list {
		flex-direction: row;
		align-items: center;
		min-height: 76px;
	}
	.recipe-card.list img,
	.recipe-card.list .photo-placeholder {
		width: 72px;
		height: 72px;
		flex-shrink: 0;
	}
	.recipe-card.recent {
		gap: 0.75rem;
		overflow-wrap: anywhere;
	}
	.recipe-card.list.recent img,
	.recipe-card.list.recent .photo-placeholder {
		width: 84px;
		height: 84px;
	}
	.photo-placeholder {
		display: grid;
		place-items: center;
		border: 1px solid var(--color-border);
		background: var(--color-surface-raised);
		color: var(--color-text-muted);
	}
	.recent h3 {
		font-weight: 600;
	}
	.recent .origin {
		color: var(--color-text-muted);
		font-size: var(--text-sm);
	}
	.recent .meta {
		display: block;
		font-family: var(--font-body);
	}
	.recipe-card-body {
		min-width: 0;
	}
	h3 {
		margin: 0;
	}
	p {
		font-family: var(--font-recipe);
		margin: 0.1rem 0 0;
	}
	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.1rem 0.7rem;
		color: var(--color-text-muted);
		font-size: var(--text-xs);
	}
	@media (max-width: 600px) {
		.recipe-card.list:not(.recent) {
			padding-block: 0.25rem;
		}
	}
</style>
