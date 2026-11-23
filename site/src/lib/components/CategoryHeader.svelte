<script lang="ts">
	import type { Category } from '$lib/types';
	import * as api from '$lib/api';
	import { ApiError } from '$lib/api';
	import { categoryNameError } from '$lib/category-errors';
	import { auth } from '$lib/stores/auth.svelte';
	import { offlineImage } from '$lib/offline/installed';
	import { loadImageFile } from '$lib/image-file';
	import Icon from './Icon.svelte';
	import PageToolbar from './PageToolbar.svelte';
	import ImageCropper from './ImageCropper.svelte';
	import Modal from './Modal.svelte';

	let {
		category: selectedCategory,
		error: categoryError = $bindable(null),
		onchanged,
		ondeleted
	}: {
		category: Category;
		error?: string | null;
		onchanged: () => Promise<void>;
		ondeleted: () => Promise<void>;
	} = $props();

	let renamingCategory = $state(false);
	let categoryCrop = $state<{ categoryId: number; file: File } | null>(null);
	let renameInput = $state('');
	let categoryBusy = $state(false);
	let showDeleteCategoryConfirm = $state(false);

	function startRenameCategory() {
		renameInput = selectedCategory.name;
		categoryError = null;
		renamingCategory = true;
	}

	function cancelRenameCategory() {
		renamingCategory = false;
		categoryCrop = null;
		categoryError = null;
	}

	async function saveCategoryRename() {
		categoryBusy = true;
		categoryError = null;
		try {
			await api.updateCategory(selectedCategory.id, { name: renameInput });
			await onchanged();
			renamingCategory = false;
		} catch (err) {
			categoryError = categoryNameError(err, 'Kategorie konnte nicht umbenannt werden.');
		} finally {
			categoryBusy = false;
		}
	}

	function pickCategoryImage(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		categoryError = null;
		categoryCrop = { categoryId: selectedCategory.id, file };
	}

	async function cropExistingCategoryImage() {
		const category = selectedCategory;
		if (!category?.image_path) return;
		categoryBusy = true;
		categoryError = null;
		try {
			const file = await loadImageFile(category.image_path, 'kategoriebild.jpg');
			if (renamingCategory && selectedCategory?.id === category.id) {
				categoryCrop = { categoryId: category.id, file };
			}
		} catch {
			categoryError = 'Kategoriebild konnte nicht geladen werden.';
		} finally {
			categoryBusy = false;
		}
	}

	async function saveCategoryImage(file: File) {
		if (!categoryCrop || categoryCrop.categoryId !== selectedCategory?.id) return;
		const { categoryId } = categoryCrop;
		categoryCrop = null;
		categoryBusy = true;
		categoryError = null;
		try {
			await api.setCategoryImage(categoryId, file);
			await onchanged();
		} catch {
			categoryError = 'Bild konnte nicht gespeichert werden (max. 20 MB, JPEG/PNG/WebP).';
		} finally {
			categoryBusy = false;
		}
	}

	async function removeCategoryImage() {
		categoryBusy = true;
		categoryError = null;
		try {
			await api.removeCategoryImage(selectedCategory.id);
			await onchanged();
		} catch {
			categoryError = 'Bild konnte nicht entfernt werden.';
		} finally {
			categoryBusy = false;
		}
	}

	async function confirmDeleteCategory() {
		categoryBusy = true;
		categoryError = null;
		try {
			await api.deleteCategory(selectedCategory.id);
			showDeleteCategoryConfirm = false;
			await ondeleted();
		} catch (err) {
			categoryError =
				err instanceof ApiError && err.status === 409
					? 'Kategorie kann nicht gelöscht werden, solange ihr Rezepte zugeordnet sind.'
					: 'Kategorie konnte nicht gelöscht werden.';
			showDeleteCategoryConfirm = false;
		} finally {
			categoryBusy = false;
		}
	}
</script>

<PageToolbar backHref="/" backLabel="Alle Kategorien">
	{#snippet actions()}
		{#if auth.hasRole('editor') && !renamingCategory}
			<a
				class="btn btn-primary btn-sm"
				href={`/recipes/new?category=${selectedCategory.id}`}
				title={`Rezept in ${selectedCategory.name} hinzufügen`}
			>
				<Icon name="plus" /> Rezept
			</a>
		{/if}
	{/snippet}
</PageToolbar>
{#if categoryError}
	<p class="alert alert-error" role="alert">{categoryError}</p>
{/if}
{#if renamingCategory && auth.hasRole('admin')}
	<form class="rename-form" onsubmit={(e) => (e.preventDefault(), saveCategoryRename())}>
		<div class="field">
			<label for="category-name">Kategoriename</label>
			<input id="category-name" type="text" bind:value={renameInput} maxlength="100" required />
		</div>
		<div class="category-image-edit">
			{#if selectedCategory.image_path}
				<img src={offlineImage(selectedCategory.image_path)} alt="" />
			{/if}
			<div class="button-row">
				<label class="btn btn-secondary btn-sm">
					{selectedCategory.image_path ? 'Bild ändern' : 'Bild hinzufügen'}
					<input
						type="file"
						accept="image/jpeg,image/png,image/webp"
						onchange={pickCategoryImage}
						disabled={categoryBusy}
						class="sr-only"
					/>
				</label>
				<label class="btn btn-secondary btn-sm">
					Foto aufnehmen
					<input
						type="file"
						accept="image/jpeg,image/png,image/webp"
						capture="environment"
						onchange={pickCategoryImage}
						disabled={categoryBusy}
						class="sr-only"
					/>
				</label>
				{#if selectedCategory.image_path}
					<button
						type="button"
						class="btn btn-secondary btn-sm"
						onclick={cropExistingCategoryImage}
						disabled={categoryBusy}
					>
						Bild zuschneiden
					</button>
					<button
						type="button"
						class="btn btn-secondary btn-sm"
						onclick={removeCategoryImage}
						disabled={categoryBusy}
					>
						Bild entfernen
					</button>
				{/if}
			</div>
		</div>
		<div class="button-row">
			<button type="submit" class="btn btn-primary btn-sm" disabled={categoryBusy}>
				{categoryBusy ? 'Speichert …' : 'Speichern'}
			</button>
			<button type="button" class="btn btn-secondary btn-sm" onclick={cancelRenameCategory}>
				Abbrechen
			</button>
		</div>
	</form>
{:else}
	<div class="page-intro category-intro">
		{#if selectedCategory.image_path}<img
				class="category-image"
				src={offlineImage(selectedCategory.image_path)}
				alt={selectedCategory.image_alt_text ?? selectedCategory.name}
			/>{/if}
		<div class="category-heading">
			<div class="category-title">
				<h1 class="display">{selectedCategory.name}</h1>
				<p class="lede">
					{(selectedCategory.recipe_count ?? 0) === 0
						? 'Noch keine Rezepte'
						: `${selectedCategory.recipe_count ?? 0} ${selectedCategory.recipe_count === 1 ? 'Rezept' : 'Rezepte'}`}
				</p>
			</div>
			{#if auth.hasRole('admin')}
				<div class="category-actions">
					<button
						class="icon-btn"
						onclick={startRenameCategory}
						title="Kategorie umbenennen"
						aria-label="Kategorie umbenennen"
					>
						<Icon name="edit" />
					</button>
					<button
						class="icon-btn danger"
						onclick={() => (showDeleteCategoryConfirm = true)}
						title="Kategorie löschen"
						aria-label="Kategorie löschen"
					>
						<Icon name="trash" />
					</button>
				</div>
			{/if}
		</div>
	</div>
{/if}

{#if categoryCrop && categoryCrop.categoryId === selectedCategory?.id && auth.hasRole('admin')}
	<ImageCropper
		file={categoryCrop.file}
		aspect={4 / 3}
		onDone={saveCategoryImage}
		onCancel={() => (categoryCrop = null)}
	/>
{/if}

{#if showDeleteCategoryConfirm && selectedCategory && auth.hasRole('admin')}
	<Modal title="Kategorie löschen?" onclose={() => (showDeleteCategoryConfirm = false)}>
		<p class="muted">
			„{selectedCategory.name}“ wird dauerhaft entfernt. Das geht nur, wenn ihr keine Rezepte mehr
			zugeordnet sind.
		</p>
		<div class="modal-actions">
			<button class="btn btn-secondary" onclick={() => (showDeleteCategoryConfirm = false)}>
				Abbrechen
			</button>
			<button class="btn btn-danger" onclick={confirmDeleteCategory} disabled={categoryBusy}>
				{categoryBusy ? 'Löscht …' : 'Endgültig löschen'}
			</button>
		</div>
	</Modal>
{/if}

<style>
	.page-intro {
		margin-bottom: 1.5rem;
		max-width: var(--measure);
	}
	.page-intro h1 {
		margin-bottom: 0.5rem;
	}
	.lede {
		margin: 0;
		color: var(--color-text-muted);
	}
	.category-intro {
		display: grid;
		gap: 0.75rem;
	}
	.category-heading {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 0.75rem;
	}
	.category-title {
		flex: 1 1 auto;
		min-width: 0;
	}
	.category-intro .lede {
		color: var(--color-primary);
	}
	.category-image {
		width: 96px;
		height: 72px;
		object-fit: cover;
		border: 1px solid var(--color-border-strong);
	}
	.category-actions,
	.button-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}
	.category-actions {
		align-self: flex-start;
		flex-wrap: nowrap;
	}
	.rename-form {
		max-width: 26rem;
		margin-bottom: 2rem;
	}
	.category-image-edit {
		margin-bottom: 1rem;
	}
	.category-image-edit label:focus-within {
		outline: 3px solid var(--color-focus);
		outline-offset: 3px;
	}
	.category-image-edit img {
		display: block;
		width: 100%;
		aspect-ratio: 4 / 3;
		object-fit: cover;
		border: 1px solid var(--color-border-strong);
		margin-bottom: 0.6rem;
	}
	@media (max-width: 600px) {
		.category-intro {
			margin-bottom: 0.75rem;
		}
		.category-image {
			width: 64px;
			height: 48px;
		}
	}
</style>
