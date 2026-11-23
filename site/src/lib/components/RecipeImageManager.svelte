<script lang="ts">
	import { tick } from 'svelte';
	import * as api from '$lib/api';
	import type { RecipeImage } from '$lib/types';
	import { loadImageFile } from '$lib/image-file';
	import ImageCropper from './ImageCropper.svelte';
	import Icon from './Icon.svelte';
	import Modal from './Modal.svelte';

	let {
		recipeId,
		version,
		images = $bindable(),
		highlight = false
	}: {
		recipeId: number;
		version: number;
		images: RecipeImage[];
		highlight?: boolean;
	} = $props();

	const MAX_IMAGES = 20;
	const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
	const accept = IMAGE_TYPES.join(',');
	const galleryId = $props.id();

	let uploading = $state(false);
	let saving = $state(false);
	let loadingCrop = $state(false);
	const busy = $derived(uploading || saving || loadingCrop);
	let uploadAltText = $state('');
	let queuedFiles: File[] = [];
	let picker: HTMLInputElement;
	let uploadOpener: HTMLElement | undefined;
	let heading: HTMLHeadingElement;
	let altTexts = $state<Record<number, string>>({});
	let panel = $state<{ id: number; kind: 'alt' | 'order' } | null>(null);
	let draggedId = $state<number | null>(null);
	let dropTarget = $state<number | null>(null);
	let fileDragDepth = $state(0);
	let announcement = $state('');
	const full = $derived(images.length >= MAX_IMAGES);
	let error = $state<string | null>(null);
	let pendingRemovalId = $state<number | null>(null);
	// Bild, das gerade zugeschnitten wird; replaceId ist gesetzt, wenn ein vorhandenes Bild ersetzt wird
	let cropping = $state<{ file: File; replaceId: number | null } | null>(null);

	function imageConflict(cause: unknown): string | null {
		return cause instanceof api.ApiError &&
			cause.status === 409 &&
			cause.detail !== null &&
			typeof cause.detail === 'object' &&
			'code' in cause.detail &&
			cause.detail.code === 'recipe_version_conflict'
			? 'Das Rezept wurde inzwischen geändert. Lade es neu, bevor du Bilder änderst.'
			: null;
	}

	function handleFileSelected(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		startUpload(Array.from(input.files ?? []), input);
		input.value = '';
	}

	function startUpload(files: File[], opener = picker) {
		if (!files.length || full || busy || cropping) return;
		error = null;
		if (files.some((file) => !IMAGE_TYPES.includes(file.type))) {
			error = 'Wähle Bilder im Format JPEG, PNG oder WebP aus.';
			return;
		}
		uploadOpener = opener;
		queuedFiles = files.slice(0, MAX_IMAGES - images.length);
		announcement = files.length > queuedFiles.length
			? `Nur die ersten ${queuedFiles.length} ausgewählten Bilder passen in die Galerie.`
			: '';
		nextUpload();
	}

	function nextUpload() {
		const file = queuedFiles.shift();
		uploadAltText = '';
		cropping = file && !full ? { file, replaceId: null } : null;
	}

	function cancelCrop() {
		queuedFiles = [];
		cropping = null;
		void restoreUploadFocus();
	}

	async function restoreUploadFocus() {
		const opener = uploadOpener;
		uploadOpener = undefined;
		await tick();
		if (opener && document.activeElement === document.body) {
			(full && opener instanceof HTMLInputElement ? heading : opener).focus();
		}
	}

	async function startCropExisting(image: RecipeImage, trigger: HTMLElement) {
		if (busy) return;
		uploadOpener = trigger;
		loadingCrop = true;
		error = null;
		try {
			cropping = { file: await loadImageFile(image.file_path, 'bild.jpg'), replaceId: image.id };
		} catch {
			error = 'Bild konnte nicht geladen werden.';
			uploadOpener = undefined;
		} finally {
			loadingCrop = false;
		}
	}

	async function uploadCropped(file: File) {
		if (!cropping) return;
		const replaceId = cropping.replaceId;
		cropping = null;
		uploading = true;
		try {
			if (replaceId === null) {
				const uploaded = await api.uploadRecipeImage(
					recipeId, file, version, uploadAltText.trim() || undefined
				);
				images = [...images, uploaded];
			} else {
				const updated = await api.cropRecipeImage(replaceId, file, version);
				images = images.map((image) => (image.id === replaceId ? updated : image));
			}
		} catch (cause) {
			queuedFiles = [];
			error = imageConflict(cause) ??
				(replaceId === null
					? 'Bild konnte nicht hochgeladen werden (max. 20 MB, JPEG/PNG/WebP).'
					: 'Der neue Bildausschnitt konnte nicht gespeichert werden.');
		} finally {
			uploading = false;
			nextUpload();
			if (!cropping) void restoreUploadFocus();
		}
	}

	function togglePanel(id: number, kind: 'alt' | 'order') {
		panel = panel?.id === id && panel.kind === kind ? null : { id, kind };
	}

	async function move(imageId: number, target: number, trigger?: HTMLButtonElement) {
		const index = images.findIndex((image) => image.id === imageId);
		if (busy || index < 0 || target < 0 || target >= images.length || index === target) return;
		const ids = images.map((image) => image.id);
		ids.splice(index, 1);
		ids.splice(target, 0, imageId);
		saving = true;
		error = null;
		try {
			images = await api.reorderRecipeImages(recipeId, ids, version);
			announcement = `Bild von Position ${index + 1} auf Position ${target + 1} verschoben.`;
			const hadFocus = document.activeElement === trigger;
			await tick();
			if (hadFocus && document.activeElement === document.body) trigger?.focus();
		} catch (cause) {
			error = imageConflict(cause) ?? 'Reihenfolge konnte nicht gespeichert werden.';
		} finally {
			saving = false;
		}
	}

	function startReorder(event: DragEvent, id: number) {
		if (busy || !event.dataTransfer) {
			event.preventDefault();
			return;
		}
		event.dataTransfer.effectAllowed = 'move';
		event.dataTransfer.setData('text/plain', String(id));
		draggedId = id;
	}

	function reorderWithArrow(event: KeyboardEvent & { currentTarget: HTMLButtonElement }, id: number, index: number) {
		if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
		if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
		event.preventDefault();
		void move(id, index + (event.key === 'ArrowUp' ? -1 : 1), event.currentTarget);
	}

	function endReorder() {
		draggedId = null;
		dropTarget = null;
	}

	function allowReorder(event: DragEvent, id: number) {
		if (busy || draggedId === null || draggedId === id) return;
		event.preventDefault();
		if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
		dropTarget = id;
	}

	function dropReorder(event: DragEvent, index: number) {
		if (draggedId === null) return;
		event.preventDefault();
		void move(draggedId, index);
		endReorder();
	}

	function allowFiles(event: DragEvent) {
		if (!event.dataTransfer?.types.includes('Files')) return;
		event.preventDefault();
		const allowed = !busy && !full && !cropping;
		event.dataTransfer.dropEffect = allowed ? 'copy' : 'none';
		if (allowed && event.type === 'dragenter') fileDragDepth++;
	}

	// Dateien, die neben der Upload-Kachel landen, dürfen den Browser nicht vom Formular wegnavigieren
	function ignoreStrayFiles(event: DragEvent) {
		if (event.defaultPrevented || !event.dataTransfer?.types.includes('Files')) return;
		event.preventDefault();
		event.dataTransfer.dropEffect = 'none';
	}

	function dropFiles(event: DragEvent) {
		event.preventDefault();
		fileDragDepth = 0;
		if (event.dataTransfer) startUpload(Array.from(event.dataTransfer.files));
	}

	async function saveAltText(image: RecipeImage) {
		const altText = (altTexts[image.id] ?? image.alt_text ?? '').trim();
		if (busy || altText === (image.alt_text ?? '')) return;
		saving = true;
		error = null;
		try {
			const updated = await api.updateRecipeImageAltText(image.id, altText || null, version);
			images = images.map((item) => (item.id === image.id ? updated : item));
			delete altTexts[image.id];
		} catch (cause) {
			error = imageConflict(cause) ?? 'Alt-Text konnte nicht gespeichert werden.';
		} finally {
			saving = false;
		}
	}

	async function makeMain(imageId: number) {
		if (busy || images.find((image) => image.id === imageId)?.is_main) return;
		saving = true;
		error = null;
		try {
			await api.setMainImage(imageId, version);
			images = images.map((image) => ({ ...image, is_main: image.id === imageId }));
		} catch (cause) {
			error = imageConflict(cause) ?? 'Hauptbild konnte nicht gespeichert werden.';
		} finally {
			saving = false;
		}
	}

	function requestRemoveImage(imageId: number) {
		if (!busy) pendingRemovalId = imageId;
	}

	function cancelRemoveImage() {
		pendingRemovalId = null;
	}

	async function confirmRemoveImage() {
		if (pendingRemovalId === null || busy) return;
		const imageId = pendingRemovalId;
		const index = images.findIndex((image) => image.id === imageId);
		pendingRemovalId = null;
		saving = true;
		error = null;
		try {
			await api.deleteRecipeImage(imageId, version);
			const removedMain = images.find((image) => image.id === imageId)?.is_main;
			images = images.filter((image) => image.id !== imageId);
			// Wie der Server: das erste verbleibende Bild wird Hauptbild
			if (removedMain && images.length > 0) {
				images = images.map((image, index) => ({ ...image, is_main: index === 0 }));
			}
			delete altTexts[imageId];
			if (panel?.id === imageId) panel = null;
			await tick();
			if (document.activeElement === document.body) {
				const next = images[Math.min(index, images.length - 1)];
				if (next) document.getElementById(`${galleryId}-remove-${next.id}`)?.focus();
				else {
					saving = false;
					await tick();
					picker.focus();
				}
			}
		} catch (cause) {
			error = imageConflict(cause) ?? 'Bild konnte nicht gelöscht werden.';
		} finally {
			saving = false;
		}
	}
</script>

<section
	class="gallery"
	aria-labelledby={`${galleryId}-heading`}
	ondragover={ignoreStrayFiles}
	ondrop={ignoreStrayFiles}
>
	<header class="gallery-heading">
		<h2 id={`${galleryId}-heading`} bind:this={heading} tabindex="-1">
			{highlight ? 'Jetzt ein Foto hinzufügen' : 'Bilder'}
		</h2>
		<p class="muted" role="status">{images.length} von {MAX_IMAGES} Bildern</p>
	</header>
	{#if highlight}
		<p class="muted">Du kannst ein Foto hinzufügen oder direkt zum Rezept gehen.</p>
	{/if}
	{#if error}
		<p class="alert alert-error" role="alert">{error}</p>
	{/if}
	<p class="sr-only" role="status">{announcement}</p>

	<ul class="image-grid" aria-label="Rezeptbilder" role="list">
		{#each images as image, index (image.id)}
			{@const altOpen = panel?.id === image.id && panel.kind === 'alt'}
			{@const orderOpen = panel?.id === image.id && panel.kind === 'order'}
			<li class="image-item">
				<div
					class="thumbnail"
					role="group"
					aria-label={`Bild ${index + 1}`}
					class:main={image.is_main}
					class:drop-target={dropTarget === image.id}
					class:dragging={draggedId === image.id}
					ondragover={(event) => allowReorder(event, image.id)}
					ondragleave={(event) => {
						if (!event.currentTarget.contains(event.relatedTarget as Node | null)) dropTarget = null;
					}}
					ondrop={(event) => dropReorder(event, index)}
				>
					<img src={image.file_path} alt={image.alt_text ?? ''} draggable="false" />
					{#if image.is_main}<span class="main-badge">Hauptbild</span>{/if}
					<button
						type="button"
						class="icon-action remove"
						id={`${galleryId}-remove-${image.id}`}
						aria-label={`Bild ${index + 1} entfernen`}
						title="Entfernen"
						aria-disabled={busy}
						onclick={() => requestRemoveImage(image.id)}
					><Icon name="trash" /></button>
					<div class="image-actions">
						<button type="button" class="icon-action" class:selected={image.is_main}
							aria-label={`Bild ${index + 1} als Hauptbild festlegen`}
							title="Als Hauptbild festlegen" aria-pressed={image.is_main}
							aria-disabled={busy || image.is_main}
							onclick={() => makeMain(image.id)}
						><Icon name="star" filled={image.is_main} /></button>
						<button type="button" class="icon-action"
							aria-label={`Bild ${index + 1} zuschneiden`} title="Zuschneiden"
							aria-disabled={busy} onclick={(event) => startCropExisting(image, event.currentTarget)}
						><Icon name="crop" /></button>
						<button type="button" class="icon-action"
							aria-label={`Alt-Text für Bild ${index + 1} bearbeiten`} title="Alt-Text bearbeiten"
							aria-expanded={altOpen} onclick={() => togglePanel(image.id, 'alt')}
						><Icon name="edit" /></button>
						{#if images.length > 1}
							<button type="button" class="icon-action grip"
								draggable={!busy}
								ondragstart={(event) => startReorder(event, image.id)}
								ondragend={endReorder}
								onkeydown={(event) => reorderWithArrow(event, image.id, index)}
								aria-label={`Bild ${index + 1} sortieren`} title="Ziehen oder Sortierung öffnen"
								aria-keyshortcuts="ArrowUp ArrowDown"
								aria-expanded={orderOpen} onclick={() => togglePanel(image.id, 'order')}
							><Icon name="grip" /></button>
						{/if}
					</div>
				</div>

				{#if altOpen}
					<div class="image-panel">
						<label class="field">
							<span>Alt-Text für Bild {index + 1}</span>
							<input type="text" maxlength="255" readonly={busy}
								value={altTexts[image.id] ?? image.alt_text ?? ''}
								oninput={(event) => (altTexts[image.id] = event.currentTarget.value)}
							/>
						</label>
						<button type="button" class="btn btn-secondary btn-sm"
							aria-label={`Alt-Text für Bild ${index + 1} speichern`}
							aria-disabled={busy || (altTexts[image.id] ?? image.alt_text ?? '').trim() === (image.alt_text ?? '')}
							onclick={() => saveAltText(image)}
						>Speichern</button>
					</div>
				{:else if orderOpen}
					<div class="image-panel order-actions" role="group" aria-label={`Bild ${index + 1} verschieben`}>
						<button type="button" class="btn btn-secondary btn-sm"
							aria-label={`Bild ${index + 1} nach vorn`}
							aria-disabled={busy || index === 0}
							onclick={(event) => move(image.id, index - 1, event.currentTarget)}
						><Icon name="up" /> Nach vorn</button>
						<button type="button" class="btn btn-secondary btn-sm"
							aria-label={`Bild ${index + 1} nach hinten`}
							aria-disabled={busy || index === images.length - 1}
							onclick={(event) => move(image.id, index + 1, event.currentTarget)}
						><Icon name="down" /> Nach hinten</button>
					</div>
				{/if}
			</li>
		{/each}
		<li class="upload-tile" class:file-target={fileDragDepth > 0}
			ondragenter={allowFiles} ondragover={allowFiles} ondrop={dropFiles}
			ondragleave={() => (fileDragDepth = Math.max(0, fileDragDepth - 1))}
		>
			<label class="upload-picker" class:unavailable={busy || full}>
				<span class="upload-plus"><Icon name="plus" /></span>
				<strong>{uploading ? 'Lädt hoch …' : 'Bilder hinzufügen'}</strong>
				<span class="upload-link">Datei auswählen</span>
				<span class="drop-hint">oder hierher ziehen</span>
				<input type="file" {accept} multiple
					aria-label="Datei auswählen" class="sr-only"
					bind:this={picker} onchange={handleFileSelected} disabled={busy || full}
				/>
			</label>
			<label class="camera-picker" class:unavailable={busy || full}>
				<Icon name="camera" /> <span class="upload-link">Foto aufnehmen</span>
				<input type="file" {accept} capture="environment"
					class="sr-only" onchange={handleFileSelected} disabled={busy || full}
				/>
			</label>
		</li>
	</ul>
	{#if full}
		<p class="muted">Maximal {MAX_IMAGES} Bilder pro Rezept. Entferne zuerst ein Bild.</p>
	{/if}
	{#if highlight}
		<a class="btn btn-primary" href={`/recipes/${recipeId}`}>Weiter zum Rezept</a>
	{/if}
</section>

{#if cropping}
	{#key cropping.file}
		<ImageCropper file={cropping.file} onDone={uploadCropped} onCancel={cancelCrop}>
			{#if cropping.replaceId === null}
				<label class="field">
					<span>Alt-Text (optional)</span>
					<input type="text" maxlength="255" bind:value={uploadAltText} />
				</label>
			{/if}
		</ImageCropper>
	{/key}
{/if}

{#if pendingRemovalId !== null}
	<Modal title="Bild entfernen?" onclose={cancelRemoveImage}>
		<p class="muted">Das Bild wird aus dem aktuellen Rezept entfernt.</p>
		<div class="modal-actions">
			<button type="button" class="btn btn-secondary" onclick={cancelRemoveImage}>Abbrechen</button>
			<button type="button" class="btn btn-danger" onclick={confirmRemoveImage}>Entfernen</button>
		</div>
	</Modal>
{/if}

<style>
	.gallery {
		margin-block-end: 1.5rem;
		container-type: inline-size;
	}

	.gallery-heading {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.25rem 1rem;
		margin-bottom: 0.75rem;
	}

	.gallery-heading > * {
		margin: 0;
	}

	.gallery-heading p {
		font-size: var(--text-sm);
		font-variant-numeric: tabular-nums;
	}

	.image-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		align-items: start;
		gap: 1rem;
		margin: 0 0 1rem;
		padding: 0;
		list-style: none;
	}

	@container (width < 310px) {
		.image-grid { grid-template-columns: minmax(0, 1fr); }
	}

	@container (width >= 640px) {
		.image-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
	}

	@container (width >= 900px) {
		.image-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
	}

	.thumbnail,
	.upload-tile {
		position: relative;
		aspect-ratio: 4 / 3;
		border-radius: 12px;
		background: var(--color-surface);
	}

	.thumbnail {
		box-shadow: 0 2px 6px color-mix(in srgb, var(--color-text) 17%, transparent);
	}

	.thumbnail.main {
		outline: 2px solid var(--color-primary);
	}

	.thumbnail.drop-target,
	.upload-tile.file-target {
		outline: 3px solid var(--color-focus);
		outline-offset: 2px;
	}

	.thumbnail.dragging {
		opacity: 0.55;
	}

	.thumbnail img {
		display: block;
		width: 100%;
		height: 100%;
		border-radius: inherit;
		object-fit: cover;
	}

	.main-badge,
	.icon-action {
		background: color-mix(in srgb, var(--color-surface-raised) 95%, transparent);
		color: var(--color-text);
		border-radius: 7px;
		box-shadow: 0 1px 4px var(--color-overlay);
	}

	.main-badge {
		position: absolute;
		inset: 6px auto auto 6px;
		padding: 0.15rem 0.45rem;
		color: var(--color-primary);
		font-size: var(--text-xs);
		font-weight: 650;
	}

	.icon-action {
		display: grid;
		place-items: center;
		width: 34px;
		height: 34px;
		border: 0;
		padding: 0;
	}

	.icon-action:hover,
	.icon-action[aria-expanded='true'] {
		background: var(--color-surface);
	}

	.icon-action.remove {
		position: absolute;
		inset: 6px 6px auto auto;
		color: var(--color-danger);
	}

	.icon-action.selected {
		color: var(--color-primary);
	}

	.icon-action.grip {
		cursor: grab;
	}

	.image-actions {
		position: absolute;
		inset: auto 0 6px;
		display: flex;
		justify-content: center;
		gap: 3px;
	}

	@media (hover: hover) and (pointer: fine) {
		.thumbnail:not(:hover):not(:focus-within) .remove,
		.thumbnail:not(:hover):not(:focus-within) .image-actions {
			opacity: 0;
		}
	}

	.image-panel {
		margin-top: 0.5rem;
		padding: 0.5rem;
		border-radius: 8px;
		background: var(--color-surface-raised);
		font-size: var(--text-sm);
	}

	.image-panel .field {
		margin-bottom: 0.5rem;
	}

	.order-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}

	.btn[aria-disabled='true'] {
		opacity: 0.65;
		cursor: default;
	}

	.upload-tile {
		display: flex;
		flex-direction: column;
		justify-content: center;
		border: 1px dashed var(--color-border-input);
		background: var(--color-surface-raised);
		text-align: center;
		font-size: var(--text-sm);
		line-height: 1.3;
	}

	.upload-picker,
	.camera-picker {
		position: relative;
		display: grid;
		justify-items: center;
		gap: 0.2rem;
		padding: 0.25rem;
		cursor: pointer;
	}

	.upload-picker:focus-within,
	.camera-picker:focus-within {
		outline: 3px solid var(--color-focus);
		outline-offset: -3px;
		border-radius: 8px;
	}

	.upload-plus {
		display: grid;
		place-items: center;
		width: 2rem;
		height: 2rem;
		border-radius: 50%;
		background: var(--color-surface);
		color: var(--color-primary);
	}

	.upload-link {
		color: var(--color-primary);
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.camera-picker,
	.drop-hint {
		display: none;
	}

	@media (hover: hover) and (pointer: fine) {
		.drop-hint {
			display: block;
			color: var(--color-text-muted);
			font-size: var(--text-xs);
		}
	}

	@media (any-pointer: coarse) {
		.camera-picker {
			display: flex;
			align-items: center;
			justify-content: center;
		}
		.camera-picker :global(.icon) {
			width: 1rem;
			height: 1rem;
		}
	}

	.unavailable {
		opacity: 0.65;
		cursor: not-allowed;
	}
</style>
