<script lang="ts">
	import { offlineImage } from '$lib/offline/installed';
	import { onMount } from 'svelte';
	import Icon from './Icon.svelte';
	import type { RecipeImage } from '$lib/types';
	import { swipeDirection, zoomScale, wrappedIndex } from '$lib/photo-gestures';
	let {
		images,
		index = $bindable(0),
		title,
		onclose
	}: { images: RecipeImage[]; index?: number; title: string; onclose: () => void } = $props();
	let dialog = $state<HTMLDialogElement>();
	const panHintId = $props.id();
	const panOffsets = new Map<string, [number, number]>([
		['ArrowLeft', [40, 0]],
		['ArrowRight', [-40, 0]],
		['ArrowUp', [0, 40]],
		['ArrowDown', [0, -40]]
	]);
	let zoomButton: HTMLButtonElement;
	let resetButton: HTMLButtonElement;
	let scale = $state(1);
	let panX = $state(0);
	let panY = $state(0);
	const pointers = new Map<number, { x: number; y: number }>();
	let startX = 0;
	let startY = 0;
	let lastX = 0;
	let lastY = 0;
	let initialDistance = 1;
	let initialScale = 1;
	let pinched = false;
	let backgroundTap = false;
	function reset() {
		if (document.activeElement === resetButton) zoomButton.focus();
		scale = 1;
		panX = 0;
		panY = 0;
	}
	function change(delta: number) {
		index = wrappedIndex(index, delta, images.length);
		reset();
	}
	function distance() {
		const [a, b] = [...pointers.values()];
		return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 1;
	}
	function down(event: PointerEvent) {
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
		pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
		if (pointers.size === 1) {
			backgroundTap = event.target === event.currentTarget;
			startX = lastX = event.clientX;
			startY = lastY = event.clientY;
			pinched = false;
		}
		if (pointers.size === 2) {
			initialDistance = distance();
			initialScale = scale;
			pinched = true;
		}
	}
	function move(event: PointerEvent) {
		if (!pointers.has(event.pointerId)) return;
		pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
		if (pointers.size === 2) {
			scale = zoomScale(initialScale, distance(), initialDistance);
			if (scale === 1) {
				panX = 0;
				panY = 0;
			}
		} else if (scale > 1) {
			panX += event.clientX - lastX;
			panY += event.clientY - lastY;
		}
		lastX = event.clientX;
		lastY = event.clientY;
	}
	function up(event: PointerEvent) {
		if (!pointers.has(event.pointerId)) return;
		pointers.delete(event.pointerId);
		lastX = event.clientX;
		lastY = event.clientY;
		if (!pinched && event.type !== 'pointercancel') {
			const direction = swipeDirection(event.clientX - startX, event.clientY - startY, scale);
			if (direction) change(direction);
		}
		const remaining = [...pointers.values()][0];
		if (remaining) {
			lastX = remaining.x;
			lastY = remaining.y;
		}
	}
	function keydown(event: KeyboardEvent & { currentTarget: HTMLDialogElement }) {
		if (event.key === 'Tab') {
			const buttons = Array.from(
				event.currentTarget.querySelectorAll<HTMLButtonElement>('button:enabled')
			);
			const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
			const next = current === -1
				? (event.shiftKey ? buttons.length - 1 : 0)
				: wrappedIndex(current, event.shiftKey ? -1 : 1, buttons.length);
			event.preventDefault();
			buttons[next].focus();
		}
		const offset = panOffsets.get(event.key);
		if (event.shiftKey && offset) {
			if (scale > 1) {
				event.preventDefault();
				panX += offset[0];
				panY += offset[1];
			}
			return;
		}
		if (event.key === 'ArrowLeft') {
			event.preventDefault();
			change(-1);
		}
		if (event.key === 'ArrowRight') {
			event.preventDefault();
			change(1);
		}
	}
	onMount(() => {
		const previous = document.activeElement as HTMLElement | null;
		const root = document.documentElement;
		const overflow = root.style.overflow;
		root.style.overflow = 'hidden';
		const viewer = dialog!;
		viewer.showModal();
		zoomButton.focus();
		return () => {
			viewer.close();
			root.style.overflow = overflow;
			previous?.focus({ preventScroll: true });
		};
	});
</script>

<dialog
	class="no-print"
	bind:this={dialog}
	aria-label={`Fotos: ${title}`}
	oncancel={(event) => {
		event.preventDefault();
		onclose();
	}}
	onkeydown={keydown}
	onclick={(event) => {
		if (event.target === dialog) onclose();
	}}
>
	<div class="viewer-toolbar">
		<p role="status">Bild {index + 1} von {images.length}</p>
		<button
			bind:this={zoomButton}
			onclick={() => {
				scale = Math.min(5, scale + 0.5);
			}}
			title="Foto vergrößern"
			aria-describedby={panHintId}
			aria-label="Foto vergrößern">Vergrößern</button
		>
		<button bind:this={resetButton} onclick={reset} disabled={scale === 1} title="Zoom zurücksetzen"
			>Originalgröße</button
		>
		<button onclick={onclose} title="Großansicht schließen" aria-label="Großansicht schließen"
			><Icon name="close" /></button
		>
	</div>
	<!-- Pointer handling is supplementary to the visible buttons and keyboard controls. -->
	<div
		class="stage"
		role="presentation"
		onpointerdown={down}
		onpointermove={move}
		onpointerup={up}
		onpointercancel={up}
		onclick={(event) => {
			if (
				backgroundTap &&
				scale === 1 &&
				event.target === event.currentTarget &&
				!pinched &&
				Math.abs(lastX - startX) < 10 &&
				Math.abs(lastY - startY) < 10
			)
				onclose();
		}}
	>
		<img
			src={offlineImage(images[index].file_path)}
			alt={images[index].alt_text ?? title}
			draggable="false"
			style:transform={`translate(${panX}px, ${panY}px) scale(${scale})`}
		/>
	</div>
	{#if images.length > 1}
		<button
			class="image-nav previous"
			onclick={() => change(-1)}
			title="Vorheriges Bild"
			aria-label="Vorheriges Bild"><Icon name="previous" /></button
		>
		<button
			class="image-nav next"
			onclick={() => change(1)}
			title="Nächstes Bild"
			aria-label="Nächstes Bild"><Icon name="next" /></button
		>
	{/if}
	<p class="hint">
		Wische zum Blättern. Ziehe zwei Finger auseinander zum Vergrößern.
		<span id={panHintId}>Im Zoom verschiebst du den Ausschnitt mit Umschalt + Pfeiltasten.</span>
	</p>
</dialog>

<style>
	dialog {
		position: fixed;
		inset: 0;
		width: 100%;
		height: 100%;
		max-width: none;
		max-height: none;
		border: none;
		margin: 0;
		padding: 1rem;
		background: transparent;
		color: var(--color-bg);
		overflow: hidden;
		overscroll-behavior: contain;
	}
	dialog::backdrop {
		background: var(--color-viewer);
	}
	dialog[open] {
		display: flex;
		flex-direction: column;
	}
	.viewer-toolbar {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		z-index: 2;
		flex-wrap: wrap;
	}
	.viewer-toolbar p {
		margin: 0 auto 0 0;
	}
	button {
		min-height: 44px;
		min-width: 44px;
		border: 1px solid var(--color-bg);
		color: var(--color-bg);
		background: var(--color-text);
		padding: 0.5rem;
		border-radius: var(--radius-sm);
		font-size: var(--text-sm);
	}
	button:focus-visible {
		outline-color: var(--color-bg);
	}
	.stage {
		display: flex;
		align-items: center;
		justify-content: center;
		flex: 1;
		min-height: 0;
		touch-action: none;
		overflow: hidden;
	}
	img {
		max-width: 100%;
		max-height: 100%;
		width: auto;
		height: auto;
		object-fit: contain;
		user-select: none;
		pointer-events: auto;
	}
	.image-nav {
		position: absolute;
		top: 50%;
		z-index: 2;
	}
	.image-nav:focus-visible {
		outline-offset: 0;
		box-shadow: 0 0 0 6px var(--color-text);
	}
	.previous {
		left: 1rem;
	}
	.next {
		right: 1rem;
	}
	.hint {
		margin: 0.5rem 0 0;
		text-align: center;
		font-size: var(--text-xs);
	}
</style>
