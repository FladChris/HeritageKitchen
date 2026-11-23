<script lang="ts">
	import { onMount } from 'svelte';
	import type { Snippet } from 'svelte';

	let {
		title,
		onclose,
		children,
		focusHeading = false
	}: { title: string; onclose: () => void; children: Snippet; focusHeading?: boolean } = $props();
	let heading: HTMLHeadingElement;
	let dialog = $state<HTMLDialogElement>();
	// A drag that starts inside (e.g. selecting text) and ends on the backdrop must not close.
	let pressedBackdrop = false;
	const titleId = $props.id();

	onMount(() => {
		const previous = document.activeElement as HTMLElement | null;
		dialog?.showModal();
		if (focusHeading) heading.focus({ preventScroll: true });
		return () => {
			dialog?.close();
			previous?.focus({ preventScroll: true });
		};
	});
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
<dialog
	bind:this={dialog}
	aria-labelledby={titleId}
	oncancel={(event) => {
		event.preventDefault();
		onclose();
	}}
	onpointerdown={(event) => {
		pressedBackdrop = event.target === dialog;
	}}
	onclick={(event) => {
		if (event.target === dialog && pressedBackdrop) onclose();
	}}
>
	<div class="modal-body">
		<!-- svelte-ignore a11y_no_noninteractive_tabindex (The heading receives programmatic focus only.) -->
		<h2 id={titleId} bind:this={heading} tabindex={focusHeading ? -1 : undefined}>{title}</h2>
		{@render children()}
	</div>
</dialog>

<style>
	dialog {
		width: min(26rem, calc(100% - 2rem));
		padding: 0;
		border: 1px solid var(--color-border-strong);
		border-radius: var(--radius-sm);
		background: var(--color-surface-raised);
		color: var(--color-text);
	}
	dialog::backdrop {
		background: var(--color-overlay);
	}
	.modal-body {
		padding: 1.5rem;
	}
	h2 {
		font-size: var(--text-lg);
	}
	.modal-body :global(.modal-actions) {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 0.75rem;
		margin-top: 1.25rem;
	}
</style>
