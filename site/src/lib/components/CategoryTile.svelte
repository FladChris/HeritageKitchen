<script lang="ts">
	import { offlineImage } from '$lib/offline/installed';
	import type { Category } from '$lib/types';
	import Icon from './Icon.svelte';
	let { category, count }: { category: Category; count: number } = $props();
</script>

<a class="category-row" href={`/?category=${category.id}`}>
	{#if category.image_path}
		<img src={offlineImage(category.image_path)} alt={category.image_alt_text ?? ''} loading="lazy" />
	{:else}
		<span class="photo-placeholder" aria-hidden="true"><Icon name="camera" /></span>
	{/if}
	<span class="name">{category.name}</span><span class="leader" aria-hidden="true"></span>
	<span class="count"
		>{count === 0 ? 'Noch keine Rezepte' : `${count} ${count === 1 ? 'Rezept' : 'Rezepte'}`}</span
	>
</a>

<style>
	.category-row {
		display: flex;
		align-items: center;
		gap: 0.8rem;
		min-height: 64px;
		padding-block: 0.5rem;
		border-bottom: 1px solid var(--color-border);
		color: var(--color-text);
	}
	.category-row:hover {
		background: var(--color-surface-raised);
		text-decoration: none;
	}
	img,
	.photo-placeholder {
		width: 56px;
		height: 56px;
		border: 1px solid var(--color-border-strong);
		flex-shrink: 0;
	}
	img {
		object-fit: cover;
	}
	.photo-placeholder {
		display: grid;
		place-items: center;
		border-color: var(--color-border);
		background: var(--color-surface-raised);
		color: var(--color-text-muted);
	}
	.name {
		font-family: var(--font-heading);
		font-size: var(--text-lg);
		overflow-wrap: anywhere;
	}
	.leader {
		flex: 1;
		min-width: 0.5rem;
		border-bottom: 1px dotted var(--color-leader);
		align-self: center;
	}
	.count {
		color: var(--color-primary);
		font-size: var(--text-sm);
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
</style>
