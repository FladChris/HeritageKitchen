<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import type { Snippet } from 'svelte';

	let {
		backHref = null,
		backLabel = 'Zurück',
		actions
	}: {
		backHref?: string | null;
		backLabel?: string;
		actions?: Snippet;
	} = $props();
</script>

<!--
	A slim, always-visible row for "where am I going back to" and the one
	primary action for this page (e.g. add a recipe). Placed at the TOP of
	the page content, above the hero, so neither needs a scroll to reach on
	a phone — the thing people asked for after finding both buried at the
	bottom of a long recipe list.
-->
<div class="page-toolbar">
	<div class="toolbar-side">
		{#if backHref}
			<a class="back-link" href={backHref}>
				<span aria-hidden="true"><Icon name="back" /></span>
				{backLabel}
			</a>
		{/if}
	</div>
	{#if actions}
		<div class="toolbar-side toolbar-actions">
			{@render actions()}
		</div>
	{/if}
</div>

<style>
	.page-toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		min-height: 44px;
		margin-bottom: 0.5rem;
	}

	.toolbar-side {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}

	.toolbar-actions {
		margin-left: auto;
	}

	.back-link {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		color: var(--color-text-muted);
		font-weight: 600;
		font-size: var(--text-sm);
		min-height: 44px;
	}

	.back-link:hover {
		color: var(--color-text);
		text-decoration: none;
	}
</style>
