<script lang="ts">
	import { tick, untrack } from 'svelte';
	import Icon from '$lib/components/Icon.svelte';

	type Item = { id: number; name: string; count?: number };
	let {
		items,
		disabled = false,
		onchange
	}: { items: Item[]; disabled?: boolean; onchange: (ids: number[]) => void } = $props();

	// The list is edited locally; the parent only learns about finished moves.
	let draft = $state<Item[]>(untrack(() => [...items]));
	let draggedId = $state<number | null>(null);
	let beforeDrag: Item[] = [];
	let list = $state<HTMLOListElement>();
	let message = $state('');

	// Pointer dragging on the grip works for mouse and touch; the arrow buttons cover keyboards.
	function startDrag(event: PointerEvent, id: number) {
		if (disabled || draggedId !== null) return;
		event.preventDefault();
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
		draggedId = id;
		beforeDrag = draft;
	}

	function dragOver(event: PointerEvent) {
		if (draggedId === null || !list) return;
		const rows = [...list.querySelectorAll<HTMLElement>('li')];
		let target = rows.findIndex((row) => {
			const rect = row.getBoundingClientRect();
			return event.clientY < rect.top + rect.height / 2;
		});
		if (target === -1) target = rows.length;
		const from = draft.findIndex((item) => item.id === draggedId);
		if (target > from) target -= 1;
		if (from === -1 || target === from || target < 0) return;
		const reordered = [...draft];
		const [moved] = reordered.splice(from, 1);
		reordered.splice(target, 0, moved);
		draft = reordered;
	}

	function endDrag() {
		if (draggedId === null) return;
		const index = draft.findIndex((item) => item.id === draggedId);
		if (index !== -1) message = `${draft[index].name}: Position ${index + 1} von ${draft.length}.`;
		draggedId = null;
		if (draft.some((item, i) => item.id !== beforeDrag[i].id)) onchange(draft.map(({ id }) => id));
	}

	function cancelDrag() {
		if (draggedId === null) return;
		draft = beforeDrag;
		draggedId = null;
	}

	async function move(index: number, direction: -1 | 1, button: HTMLButtonElement) {
		const target = index + direction;
		if (target < 0 || target >= draft.length || disabled || draggedId !== null) return;
		const focused = document.activeElement === button;
		const row = button.closest('li');
		const reordered = [...draft];
		[reordered[index], reordered[target]] = [reordered[target], reordered[index]];
		draft = reordered;
		message = `${reordered[target].name}: Position ${target + 1} von ${reordered.length}.`;
		onchange(reordered.map(({ id }) => id));
		if (focused) {
			await tick();
			if (document.activeElement === button || document.activeElement === document.body) {
				(button.disabled ? row?.querySelector<HTMLButtonElement>('button:enabled') : button)?.focus();
			}
		}
	}
</script>

<ol
	class="order-list"
	bind:this={list}
	onpointermove={dragOver}
	onpointerup={endDrag}
	onpointercancel={cancelDrag}
>
	{#each draft as item, index (item.id)}
		<li class:dragging={draggedId === item.id}>
			<span class="grip" aria-hidden="true" onpointerdown={(event) => startDrag(event, item.id)}
				><Icon name="grip" /></span
			>
			<span class="order-name">{item.name}</span>
			{#if item.count !== undefined}<span class="order-count">{item.count}</span>{/if}
			<button
				class="icon-btn"
				aria-label={`${item.name} nach oben`}
				title="Nach oben"
				disabled={index === 0 || disabled}
				onclick={(event) => move(index, -1, event.currentTarget)}><Icon name="up" /></button
			>
			<button
				class="icon-btn"
				aria-label={`${item.name} nach unten`}
				title="Nach unten"
				disabled={index === draft.length - 1 || disabled}
				onclick={(event) => move(index, 1, event.currentTarget)}><Icon name="down" /></button
			>
		</li>
	{/each}
</ol>
<p class="sr-only" role="status">{message}</p>

<style>
	.order-list {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.order-list li {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-height: 64px;
		padding-block: 0.4rem;
		border-bottom: 1px solid var(--color-border);
		background: var(--color-bg);
	}
	.order-list li.dragging {
		background: var(--color-surface-raised);
		outline: 1px solid var(--color-border-input);
	}
	.grip {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		flex-shrink: 0;
		color: var(--color-text-muted);
		cursor: grab;
		touch-action: none;
	}
	.dragging .grip {
		cursor: grabbing;
	}
	.order-name {
		flex: 1;
		min-width: 0;
		font-family: var(--font-heading);
		font-size: var(--text-lg);
		overflow-wrap: anywhere;
	}
	.order-count {
		color: var(--color-text-muted);
		font-size: var(--text-sm);
		font-variant-numeric: tabular-nums;
		margin-right: 0.25rem;
	}
</style>
