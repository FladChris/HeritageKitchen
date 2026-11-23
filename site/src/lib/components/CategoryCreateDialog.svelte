<script lang="ts">
	import * as api from '$lib/api';
	import { categoryNameError } from '$lib/category-errors';
	import Modal from './Modal.svelte';

	let { oncreated, onclose }: {
		oncreated: () => Promise<void>;
		onclose: () => void;
	} = $props();

	let createNameInput = $state('');
	let categoryBusy = $state(false);
	let createCategoryError = $state<string | null>(null);

	async function submitCreateCategory(event: SubmitEvent) {
		event.preventDefault();
		categoryBusy = true;
		createCategoryError = null;
		try {
			await api.createCategory({ name: createNameInput });
			await oncreated();
		} catch (err) {
			createCategoryError = categoryNameError(err, 'Kategorie konnte nicht angelegt werden.');
		} finally {
			categoryBusy = false;
		}
	}
</script>

<Modal title="Neue Kategorie" onclose={onclose}>
	<form onsubmit={submitCreateCategory}>
		{#if createCategoryError}
			<p class="alert alert-error" role="alert">{createCategoryError}</p>
		{/if}
		<div class="field">
			<label for="new-category-name">Name</label>
			<input
				id="new-category-name"
				type="text"
				bind:value={createNameInput}
				maxlength="100"
				required
			/>
		</div>
		<div class="modal-actions">
			<button
				type="button"
				class="btn btn-secondary"
				onclick={onclose}
			>
				Abbrechen
			</button>
			<button type="submit" class="btn btn-primary" disabled={categoryBusy}>
				{categoryBusy ? 'Speichert …' : 'Anlegen'}
			</button>
		</div>
	</form>
</Modal>
