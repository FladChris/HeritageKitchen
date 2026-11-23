<script lang="ts">
	import { offline } from '$lib/stores/offline.svelte';
	import { onMount, tick } from 'svelte';
	import {
		ApiError,
		createRecipeComment,
		deleteRecipeComment,
		listRecipeComments,
		updateRecipeComment
	} from '$lib/api';
	import type { RecipeComment, User } from '$lib/types';

	let { recipeId, user }: { recipeId: number; user: User | null } = $props();
	const headingId = $props.id();
	const dateFormat = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' });
	const activeUser = $derived(user?.is_active && !offline.offline ? user : null);
	let comments = $state<RecipeComment[]>([]);
	let loading = $state(true);
	let loadFailed = $state(false);
	let busy = $state(false);
	let error = $state('');
	let draft = $state('');
	let editDraft = $state('');
	let editingId = $state<number | null>(null);
	let editInput: HTMLTextAreaElement | undefined = $state();
	let draftInput: HTMLTextAreaElement | undefined = $state();

	onMount(() => void load());

	async function load() {
		loading = true;
		loadFailed = false;
		try {
			comments = await listRecipeComments(recipeId);
		} catch {
			loadFailed = true;
		} finally {
			loading = false;
		}
	}

	async function mutate(action: () => Promise<void>, failureMessage: string) {
		if (busy) return false;
		busy = true;
		error = '';
		try {
			await action();
			return true;
		} catch (cause) {
			error = cause instanceof ApiError ? cause.message : failureMessage;
			return false;
		} finally {
			busy = false;
		}
	}

	async function post(event: SubmitEvent) {
		event.preventDefault();
		const text = draft.trim();
		if (!text) return;
		const posted = await mutate(async () => {
			const comment = await createRecipeComment(recipeId, text);
			comments = [...comments, comment];
			draft = '';
		}, 'Der Kommentar konnte nicht veröffentlicht werden.');
		if (posted) {
			await tick();
			draftInput?.focus();
		}
	}

	async function beginEdit(comment: RecipeComment) {
		error = '';
		editingId = comment.id;
		editDraft = comment.text;
		await tick();
		editInput?.focus();
	}

	async function finishEdit(commentId: number) {
		editingId = null;
		error = '';
		await tick();
		document.getElementById(`${headingId}-edit-${commentId}`)?.focus();
	}

	async function saveEdit(event: SubmitEvent, commentId: number) {
		event.preventDefault();
		const text = editDraft.trim();
		if (!text) return;
		const saved = await mutate(async () => {
			const edited = await updateRecipeComment(recipeId, commentId, text);
			comments = comments.map((comment) => (comment.id === edited.id ? edited : comment));
		}, 'Der Kommentar konnte nicht gespeichert werden.');
		if (saved) await finishEdit(commentId);
	}

	async function remove(commentId: number) {
		const deleted = await mutate(async () => {
			await deleteRecipeComment(recipeId, commentId);
			comments = comments.filter((comment) => comment.id !== commentId);
		}, 'Der Kommentar konnte nicht gelöscht werden.');
		if (deleted) {
			await tick();
			draftInput?.focus();
		}
	}
</script>

<section class="comments no-print" aria-labelledby={headingId} aria-busy={loading}>
	<h2 id={headingId}>Kommentare</h2>
	{#if loading}
		<p class="muted">Kommentare werden geladen …</p>
	{:else if loadFailed}
		<p class="alert alert-error" role="alert">Kommentare konnten nicht geladen werden.</p>
		<button class="btn btn-secondary" type="button" onclick={load}>Erneut laden</button>
	{:else}
		{#if comments.length}
			<ol role="list">
				{#each comments as comment (comment.id)}
					{@const own = activeUser !== null && activeUser.id === comment.author_id}
					<li>
						<div class="meta">
							<strong>{comment.author_username ?? 'Gelöschter Benutzer'}</strong>
							<time class="muted" datetime={comment.created_at}>
								{dateFormat.format(new Date(comment.created_at))}
							</time>
							{#if comment.edited_at}<span class="muted">Bearbeitet von {comment.author_username ?? 'Gelöschter Benutzer'}</span>{/if}
						</div>
						{#if own && editingId === comment.id}
							<form onsubmit={(event) => saveEdit(event, comment.id)}>
								<div class="field">
									<label for={`${headingId}-edit-text`}>Kommentar bearbeiten</label>
									<textarea
										id={`${headingId}-edit-text`}
										rows="3"
										required
										maxlength={5000}
										readonly={busy}
										bind:this={editInput}
										bind:value={editDraft}
									></textarea>
								</div>
								<div class="actions">
									<button class="btn btn-primary" disabled={busy || !editDraft.trim()}>
										Speichern
									</button>
									<button
										type="button"
										class="btn btn-quiet"
										disabled={busy}
										onclick={() => finishEdit(comment.id)}
									>
										Abbrechen
									</button>
								</div>
							</form>
						{:else}
							<p class="comment-text">{comment.text}</p>
							{#if own || activeUser?.role === 'admin'}
								<div class="actions">
									{#if own}
										<button
											id={`${headingId}-edit-${comment.id}`}
											type="button"
											class="btn btn-quiet"
											disabled={busy || editingId !== null}
											onclick={() => beginEdit(comment)}
										>
											Kommentar bearbeiten
										</button>
									{/if}
									<button
										type="button"
										class="btn btn-quiet"
										disabled={busy || editingId !== null}
										onclick={() => remove(comment.id)}
									>
										Kommentar löschen
									</button>
								</div>
							{/if}
						{/if}
					</li>
				{/each}
			</ol>
		{:else}
			<p class="muted">Noch keine Kommentare.</p>
		{/if}
		{#if error}<p class="alert alert-error" role="alert">{error}</p>{/if}
		{#if activeUser}
			<form class="compose" onsubmit={post}>
				<div class="field">
					<label for={`${headingId}-draft`}>Dein Kommentar</label>
					<textarea
						id={`${headingId}-draft`}
						rows="3"
						required
						maxlength={5000}
						readonly={busy}
						bind:this={draftInput}
						bind:value={draft}
					></textarea>
				</div>
				<button class="btn btn-primary" disabled={busy || !draft.trim()}>
					Kommentar veröffentlichen
				</button>
			</form>
		{/if}
	{/if}
</section>

<style>
	.comments {
		max-width: var(--measure);
		margin-block-start: 2rem;
	}
	ol {
		list-style: none;
		padding: 0;
	}
	li {
		border-block-start: 1px solid var(--color-border);
		padding-block: 1rem;
		overflow-wrap: anywhere;
	}
	li:last-child {
		border-block-end: 1px solid var(--color-border);
	}
	.meta,
	.actions {
		display: flex;
		align-items: baseline;
		flex-wrap: wrap;
		gap: 0.25rem 0.75rem;
	}
	.meta time,
	.meta span {
		font-size: var(--text-sm);
	}
	.comment-text {
		white-space: pre-wrap;
		margin-block: 0.35rem 0;
	}
	li form,
	li .actions {
		margin-block-start: 0.5rem;
	}
	.compose {
		margin-block-start: 1rem;
	}
</style>
