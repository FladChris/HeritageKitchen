<script lang="ts">
	import type { ViewPreferences } from '$lib/types';
	import Icon from './Icon.svelte';

	type View = ViewPreferences['recipe_view'];
	let { view, disabled = false, onchange }: {
		view: View;
		disabled?: boolean;
		onchange: (view: View) => void;
	} = $props();
</script>

<div class="view-toggle" role="group" aria-label="Ansicht">
	<button
		type="button"
		class="icon-btn"
		onclick={() => onchange('grid')}
		{disabled}
		aria-pressed={view === 'grid'}
		title="Kachelansicht"
		aria-label="Kachelansicht"
	>
		<Icon name="grid" />
	</button>
	<button
		type="button"
		class="icon-btn"
		onclick={() => onchange('list')}
		{disabled}
		aria-pressed={view === 'list'}
		title="Listenansicht"
		aria-label="Listenansicht"
	>
		<Icon name="list" />
	</button>
</div>
