<script lang="ts">
	import type { Category, RecipeConflict, RecipeInput } from '$lib/types';
	import Modal from './Modal.svelte';
	import { recipeFieldLabels } from '$lib/recipe-field-labels';

	let {
		conflict,
		draft,
		categories = [],
		busy,
		oncontinue,
		onleave,
		onoverwrite
	}: {
		conflict: RecipeConflict;
		draft: RecipeInput;
		categories?: Category[];
		busy: boolean;
		oncontinue: () => void;
		onleave: () => void;
		onoverwrite: () => void;
	} = $props();

	const labels: Readonly<Record<string, string>> = {
		...recipeFieldLabels,
		steps: 'Zubereitungsschritte',
		images: 'Rezeptbilder'
	};

	const changes = $derived(Object.entries(conflict.changes));

	function formatItem(item: unknown): string {
		if (item === null || typeof item !== 'object') return String(item);
		const entry = item as Record<string, unknown>;
		if (typeof entry.instruction === 'string') {
			return [entry.heading, entry.instruction].filter(Boolean).join(': ');
		}
		const quantity = [entry.amount, entry.unit].filter((part) => part !== null && part !== undefined && part !== '');
		const name = typeof entry.name === 'string' ? entry.name : '';
		return [quantity.join(' '), name, entry.note ? `(${entry.note})` : ''].filter(Boolean).join(' ');
	}

	function formatValue(value: unknown): string {
		if (value === null || value === undefined || value === '') return '–';
		if (typeof value === 'boolean') return value ? 'Ja' : 'Nein';
		if (Array.isArray(value)) {
			return value.length === 0 ? '–' : value.map((item, index) => `${index + 1}. ${formatItem(item)}`).join('\n');
		}
		if (typeof value === 'object') return JSON.stringify(value, null, 2);
		return String(value);
	}

	function localValue(field: string): string {
		if (field === 'images') return 'Bilder werden separat im Bildmanager verwaltet.';
		if (field === 'category_name') {
			return categories.find((category) => category.id === draft.category_id)?.name ?? '–';
		}
		return formatValue((draft as unknown as Record<string, unknown>)[field]);
	}
</script>

<Modal title="Rezept wurde zwischenzeitlich geändert" onclose={oncontinue} focusHeading>
	<p role="status">
		Deine Änderungen wurden nicht gespeichert. Version {conflict.expected_version} ist nicht mehr
		aktuell; auf dem Server liegt Version {conflict.current_version}.
	</p>
	<p class="muted">
		Vergleiche die Änderungen, bevor du entscheidest. Dein Entwurf bleibt im Formular erhalten.
		Es wird nichts automatisch zusammengeführt.
	</p>

	{#if changes.length === 0}
		<p>Seit dem Öffnen wurden keine sichtbaren Rezeptfelder verändert.</p>
	{:else}
		<!-- svelte-ignore a11y_no_noninteractive_tabindex (The differences can overflow and must be keyboard-scrollable.) -->
		<section class="conflict-differences" aria-label="Geänderte Rezeptfelder" tabindex="0">
			{#each changes as [field, change] (field)}
				<section class="conflict-field">
					<h3>{labels[field] ?? field}</h3>
					<p><strong>Beim Öffnen:</strong></p>
					<pre>{formatValue(change.before)}</pre>
					<p><strong>Jetzt auf dem Server:</strong></p>
					<pre>{formatValue(change.after)}</pre>
					<p><strong>Mein Entwurf:</strong></p>
					<pre>{localValue(field)}</pre>
				</section>
			{/each}
		</section>
	{/if}

	<details>
		<summary>Aktuellen vollständigen Rezeptstand ansehen</summary>
		<pre>{formatValue(conflict.current)}</pre>
	</details>

	<div class="modal-actions">
		<button type="button" class="btn btn-secondary" onclick={oncontinue} disabled={busy}
			>Weiter bearbeiten</button
		>
		<button type="button" class="btn btn-secondary" onclick={onleave} disabled={busy}
			>Bearbeitung verlassen</button
		>
		<button type="button" class="btn btn-primary" onclick={onoverwrite} disabled={busy}
			>Trotzdem überschreiben</button
		>
	</div>
</Modal>

<style>
	.conflict-differences {
		max-height: min(50vh, 26rem);
		overflow: auto;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
	}
	.conflict-field {
		padding: 0.75rem;
		border-bottom: 1px solid var(--color-border);
	}
	.conflict-field:last-child {
		border-bottom: 0;
	}
	.conflict-field h3 { margin: 0 0 0.5rem; }
	.conflict-field p { margin: 0.4rem 0 0; }
	pre {
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		font: inherit;
		font-size: var(--text-sm);
		margin: 0.25rem 0 0.5rem;
	}
	details { margin-top: 1rem; }
</style>
