<script lang="ts">
	import { onMount, type Snippet } from 'svelte';
	import Cropper from 'cropperjs';
	import 'cropperjs/dist/cropper.css';

	let {
		file,
		aspect = NaN,
		allowAspectChoice = true,
		embedded = false,
		saveLabel = 'Zuschneiden und speichern',
		minSize,
		disabled = false,
		children,
		onDone,
		onCancel
	}: {
		file: File;
		aspect?: number;
		allowAspectChoice?: boolean;
		embedded?: boolean;
		saveLabel?: string;
		minSize?: number;
		disabled?: boolean;
		children?: Snippet;
		onDone: (file: File) => void;
		onCancel: () => void;
	} = $props();

	const aspectChoices = [
		{ label: 'Frei', value: NaN },
		{ label: '4:3', value: 4 / 3 },
		{ label: '16:9', value: 16 / 9 },
		{ label: '1:1', value: 1 }
	];

	let dialog = $state<HTMLDialogElement>();
	let imageElement: HTMLImageElement;
	let cropper: Cropper | null = null;
	// der Dialog wird pro Bild neu angelegt, Startwerte reichen
	// svelte-ignore state_referenced_locally
	let currentAspect = $state(aspect);
	let busy = $state(false);
	const keyboardHelp = $props.id();
	// svelte-ignore state_referenced_locally
	const imageUrl = URL.createObjectURL(file);

	onMount(() => {
		const opener = document.activeElement as HTMLElement | null;
		if (!embedded) dialog?.showModal();
		cropper = new Cropper(imageElement, {
			aspectRatio: currentAspect,
			viewMode: 1,
			autoCropArea: 1,
			minCropBoxWidth: 1,
			minCropBoxHeight: 1,
			background: false,
			dragMode: 'none',
			toggleDragModeOnDblclick: false,
			zoomable: false
		});
		return () => {
			cropper?.destroy();
			if (!embedded) {
				dialog?.close();
				opener?.focus({ preventScroll: true });
			}
			URL.revokeObjectURL(imageUrl);
		};
	});

	function chooseAspect(value: number) {
		currentAspect = value;
		cropper?.setAspectRatio(value);
	}

	function adjustCrop(event: KeyboardEvent) {
		const direction = {
			ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]
		}[event.key];
		if (!direction || event.altKey || event.ctrlKey || event.metaKey || !cropper || disabled || busy) return;
		const { left, top, width, height } = cropper.getCropBoxData();
		if (!width || !height) return;
		event.preventDefault();
		const [x, y] = direction;
		if (!event.shiftKey) {
			cropper.setCropBoxData({ left: left + x * 10, top: top + y * 10 });
			return;
		}
		const widthChange = (x || y * currentAspect) * 10;
		cropper.setCropBoxData(Number.isFinite(currentAspect)
			? { width: width + widthChange, height: height + widthChange / currentAspect }
			: { width: width + x * 10, height: height + y * 10 });
	}

	function save() {
		if (!cropper || busy || disabled) return;
		const canvas = cropper.getCroppedCanvas({
			minWidth: minSize,
			minHeight: minSize,
			maxWidth: 2400,
			maxHeight: 2400
		});
		if (!canvas) return;
		busy = true;
		canvas.toBlob(
			(blob) => {
				busy = false;
				if (!blob) return;
				onDone(new File([blob], 'bild.jpg', { type: 'image/jpeg' }));
			},
			'image/jpeg',
			0.9
		);
	}
</script>

{#snippet cropperContent()}
	{#if !embedded}<h3>Bild zuschneiden</h3>{/if}
	<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions (The custom crop frame needs focus and arrow-key input.) -->
	<div
		class="cropper-area"
		role="application"
		aria-label="Zuschnittrahmen"
		aria-describedby={keyboardHelp}
		tabindex={0}
		onkeydown={adjustCrop}
	>
		<img bind:this={imageElement} src={imageUrl} alt="Vorschau zum Zuschneiden" />
	</div>
	<p id={keyboardHelp} class="muted">Pfeiltasten verschieben den Rahmen. Umschalt + Pfeiltasten ändern seine Größe.</p>
	{#if allowAspectChoice}<div class="cropper-tools">
			{#each aspectChoices as choice (choice.label)}
				<button
					type="button"
					class="btn btn-secondary btn-sm"
					class:active={Object.is(currentAspect, choice.value)}
					aria-pressed={Object.is(currentAspect, choice.value)}
					onclick={() => chooseAspect(choice.value)}
				>
					{choice.label}
				</button>
			{/each}
	</div>{/if}
	{@render children?.()}
	<div class="cropper-actions">
		<button type="button" class="btn btn-secondary" onclick={onCancel} {disabled}>Abbrechen</button>
		<button type="button" class="btn btn-primary" onclick={save} disabled={busy || disabled}>
			{busy || disabled ? 'Speichert …' : saveLabel}
		</button>
	</div>
{/snippet}

{#if embedded}
	<div class="embedded">{@render cropperContent()}</div>
{:else}
	<dialog
		bind:this={dialog}
		class="cropper-backdrop"
		aria-label="Bild zuschneiden"
		oncancel={(event) => {
			event.preventDefault();
			if (!busy) onCancel();
		}}
	>
		<div class="cropper-dialog card">{@render cropperContent()}</div>
	</dialog>
{/if}

<style>
	.cropper-backdrop {
		position: fixed;
		inset: 0;
		z-index: 100;
		width: 100%;
		height: 100%;
		max-width: none;
		max-height: none;
		margin: 0;
		padding: 1rem;
		border: 0;
		color: var(--color-text);
		background: var(--color-overlay);
		overflow: auto;
	}

	.cropper-backdrop[open] {
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.cropper-backdrop::backdrop {
		background: var(--color-overlay);
	}

	.cropper-dialog {
		background: var(--color-surface-raised);
		width: min(900px, 100%);
		max-height: 100%;
		overflow: auto;
		padding: 1.25rem;
	}

	.cropper-area {
		height: min(55vh, 520px);
		margin: 0.75rem 0;
	}

	.cropper-area img {
		display: block;
		max-width: 100%;
	}

	.embedded .cropper-area {
		height: min(34vh, 18rem);
	}

	.cropper-tools,
	.cropper-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}


	.cropper-actions {
		justify-content: flex-end;
		margin-top: 1rem;
	}

	.cropper-tools .active {
		background: var(--color-primary);
		border-color: var(--color-primary);
		color: var(--color-primary-contrast);
	}
</style>
