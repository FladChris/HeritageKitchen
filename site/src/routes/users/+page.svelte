<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import { cookbook } from '$lib/stores/settings.svelte';
	import { onMount, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import * as api from '$lib/api';
	import { ApiError } from '$lib/api';
	import { auth } from '$lib/stores/auth.svelte';
	import type { User, UserRole } from '$lib/types';
	import Modal from '$lib/components/Modal.svelte';
	import PasswordInput from '$lib/components/PasswordInput.svelte';

	let users = $state<User[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let resetAvailable = $state(false);
	let emailHint = $state('');
	let resetFeedback = $state('');
	let savingId = $state<number | null>(null);
	let registrationToReject = $state<User | null>(null);
	let userToDelete = $state<User | null>(null);
	let newUserButton = $state<HTMLButtonElement>();
	const activeAdminCount = $derived(
		users.filter((user) => user.role === 'admin' && user.is_active).length
	);

	let showNewForm = $state(false);
	let newUsername = $state('');
	let newPassword = $state('');
	let newEmail = $state('');
	let resetId = $state<number | null>(null);
	let resetValue = $state('');
	let newRole = $state<UserRole>('reader');
	let creating = $state(false);

	async function load() {
		loading = true;
		try {
			users = await api.listUsers();
		} catch {
			error = 'Benutzer konnten nicht geladen werden.';
		} finally {
			loading = false;
		}
	}

	async function saveUser(
		user: User,
		changes: { role: UserRole } | { is_active: boolean },
		fallback: string
	) {
		savingId = user.id;
		error = null;
		try {
			const updated = await api.updateUser(user.id, changes);
			if (user.id === auth.user?.id && (updated.role !== 'admin' || !updated.is_active)) {
				await auth.refresh();
				await goto('/');
				return true;
			}
			await load();
			return true;
		} catch (err) {
			error = err instanceof ApiError ? err.message : fallback;
			return false;
		} finally {
			savingId = null;
		}
	}

	async function changeRole(user: User, select: HTMLSelectElement) {
		if (
			!(await saveUser(
				user,
				{ role: select.value as UserRole },
				'Rolle konnte nicht geändert werden.'
			))
		) {
			select.value = user.role;
		}
	}

	function toggleActive(user: User) {
		return saveUser(user, { is_active: !user.is_active }, 'Status konnte nicht geändert werden.');
	}

	async function confirmRejection() {
		const user = registrationToReject;
		if (!user || savingId !== null) return;

		registrationToReject = null;
		savingId = user.id;
		error = null;
		try {
			await api.rejectRegistration(user.id);
			await load();
		} catch (err) {
			error =
				err instanceof ApiError ? err.message : 'Registrierung konnte nicht abgelehnt werden.';
			if (err instanceof ApiError && (err.status === 404 || err.status === 409)) await load();
		} finally {
			savingId = null;
		}
	}

	function isLastActiveAdmin(user: User) {
		return user.role === 'admin' && user.is_active && activeAdminCount === 1;
	}

	function closeDeleteDialog() {
		if (savingId === null) userToDelete = null;
	}

	async function confirmDeletion() {
		const user = userToDelete;
		if (!user || savingId !== null || isLastActiveAdmin(user)) return;

		savingId = user.id;
		error = null;
		try {
			await api.deleteUser(user.id);
			userToDelete = null;
			if (user.id === auth.user?.id) {
				await auth.refresh();
				await goto('/', { invalidateAll: true });
				return;
			}
			await load();
			await tick();
			newUserButton?.focus();
		} catch (err) {
			userToDelete = null;
			error = err instanceof ApiError ? err.message : 'Benutzer konnte nicht gelöscht werden.';
		} finally {
			savingId = null;
		}
	}

	async function handleCreate(event: SubmitEvent) {
		event.preventDefault();
		creating = true;
		error = null;
		try {
			await api.createUser({
				username: newUsername,
				email: resetAvailable ? newEmail.trim() || null : null,
				password: newPassword,
				role: newRole
			});
			showNewForm = false;
			newUsername = '';
			newPassword = '';
			newEmail = '';
			newRole = 'reader';
			await load();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Benutzer konnte nicht erstellt werden.';
		} finally {
			creating = false;
		}
	}

	async function setPassword(user: User) {
		savingId = user.id;
		error = null;
		try {
			await api.updateUser(user.id, { password: resetValue });
			resetId = null;
			resetValue = '';
		} catch {
			error = 'Passwort konnte nicht gesetzt werden.';
		} finally {
			savingId = null;
		}
	}

	async function sendPasswordReset(user: User) {
		savingId = user.id;
		error = null;
		resetFeedback = '';
		try {
			await api.sendUserPasswordReset(user.id);
			resetFeedback = 'Der SMTP-Server hat die Reset-E-Mail angenommen.';
		} catch (err) {
			error =
				err instanceof ApiError ? err.message : 'Die Reset-E-Mail konnte nicht gesendet werden.';
			loadResetAvailability();
		} finally {
			savingId = null;
		}
	}

	async function loadResetAvailability() {
		try {
			const result = await api.resetAvailable();
			resetAvailable = result.available;
			emailHint = result.hint ?? '';
		} catch {
			resetAvailable = false;
			emailHint = '';
		}
	}

	onMount(async () => {
		await auth.init();
		if (!auth.hasRole('admin')) {
			goto('/');
			return;
		}
		load();
		loadResetAvailability();
	});
</script>

<svelte:head>
	<title>Benutzerverwaltung &middot; {cookbook.settings.cookbook_name}</title>
</svelte:head>

{#if auth.hasRole('admin')}
	<div class="page-header">
		<h1>Benutzerverwaltung</h1>
		<button
			class="btn btn-primary"
			bind:this={newUserButton}
			onclick={() => (showNewForm = !showNewForm)}
		>
			<Icon name="plus" /> Neuer Benutzer
		</button>
	</div>

	{#if error}
		<p class="alert alert-error" role="alert">{error}</p>
	{/if}
	{#if resetFeedback}
		<p class="alert alert-success" role="status">{resetFeedback}</p>
	{/if}

	{#if showNewForm}
		<form class="card user-form" onsubmit={handleCreate}>
			<div class="field">
				<label for="new-username">Benutzername</label>
				<input
					id="new-username"
					type="text"
					bind:value={newUsername}
					minlength={3}
					maxlength={32}
					required
				/>
			</div>
			<div class="field">
				<label for="new-password">Passwort</label>
				<PasswordInput id="new-password" bind:value={newPassword} required minlength={8} />
			</div>
			<div class="field">
				<label for="new-email">E-Mail (optional)</label>
				<input
					id="new-email"
					type="email"
					bind:value={newEmail}
					disabled={!resetAvailable || creating}
					aria-describedby="new-email-hint"
				/>
				<small id="new-email-hint" class="muted">
					{resetAvailable
						? 'An diese Adresse wird ein Bestätigungslink gesendet.'
						: emailHint || 'E-Mail ist erst verfügbar, wenn SMTP eingerichtet und getestet ist.'}
				</small>
			</div>
			<div class="field">
				<label for="new-role">Rolle</label>
				<select id="new-role" bind:value={newRole}>
					<option value="reader">Leser</option>
					<option value="editor">Redakteur</option>
					<option value="admin">Administrator</option>
				</select>
			</div>
			<button class="btn btn-primary" type="submit" disabled={creating}>
				{creating ? 'Erstellt …' : 'Benutzer anlegen'}
			</button>
		</form>
	{/if}

	{#if loading}
		<p class="muted">Lädt …</p>
	{:else}
		<div class="user-table-wrap">
			<table class="user-table">
				<thead>
					<tr>
						<th>Benutzername</th>
						<th>E-Mail</th>
						<th>Rolle</th>
						<th>Status</th>
						<th><span class="sr-only">Aktionen</span></th>
					</tr>
				</thead>
				<tbody>
					{#each users as user (user.id)}
						<tr>
							<td class="user-name">{user.username}</td>
							<td data-label="E-Mail">
								{#if user.email}
									<div>
										{user.email}<br /><small class="muted">
											{resetAvailable && user.email_verified_at ? 'Bestätigt' : 'Unbestätigt'}
										</small>
									</div>
								{:else}–{/if}
							</td>
							<td data-label="Rolle">
								<select
									aria-label={`Rolle von ${user.username}`}
									value={user.role}
									disabled={user.pending_approval || savingId !== null || isLastActiveAdmin(user)}
									onchange={(e) => changeRole(user, e.currentTarget)}
								>
									<option value="reader">Leser</option>
									<option value="editor">Redakteur</option>
									<option value="admin">Administrator</option>
								</select>
							</td>
							<td data-label="Status">
								{user.pending_approval
									? 'Wartet auf Freischaltung'
									: user.is_active
										? 'Aktiv'
										: 'Deaktiviert'}
							</td>
							<td>
								<div class="user-actions">
									{#if resetId === user.id}
										<form onsubmit={(event) => (event.preventDefault(), setPassword(user))}>
											<PasswordInput
												id={`reset-${user.id}`}
												aria-label={`Neues Passwort für ${user.username}`}
												bind:value={resetValue}
												autocomplete="new-password"
												minlength={8}
												required
											/>
											<button
												class="btn btn-secondary btn-sm"
												type="submit"
												disabled={savingId === user.id}>Speichern</button
											>
										</form>
									{:else}
										<button class="btn btn-secondary btn-sm btn-compact" onclick={() => (resetId = user.id)}
											>Passwort setzen</button
										>
									{/if}
									{#if resetAvailable && user.email && user.email_verified_at && user.is_active}
										<button
											class="btn btn-secondary btn-sm"
											onclick={() => sendPasswordReset(user)}
											disabled={savingId !== null}>Reset-Link senden</button
										>
									{/if}
									<button
										class="btn btn-secondary btn-sm btn-compact"
										onclick={() => toggleActive(user)}
										disabled={savingId !== null || isLastActiveAdmin(user)}
									>
										{user.pending_approval
											? 'Freischalten'
											: user.is_active
												? 'Deaktivieren'
												: 'Aktivieren'}
									</button>
									{#if user.pending_approval}
										<button
											class="btn btn-danger btn-sm"
											onclick={() => (registrationToReject = user)}
											disabled={savingId !== null}
										>
											Ablehnen
										</button>
									{:else}
										<button
											class="btn btn-danger btn-sm btn-compact"
											onclick={() => (userToDelete = user)}
											disabled={savingId !== null || isLastActiveAdmin(user)}
										>
											Benutzer löschen
										</button>
									{/if}
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

	{#if userToDelete}
		<Modal title="Benutzer löschen?" onclose={closeDeleteDialog}>
			<p class="muted">
				Das Konto „{userToDelete.username}“ wird endgültig gelöscht. Rezepte und Kommentare bleiben erhalten. In Kommentaren erscheint der Name
				„Gelöschter Benutzer“. Persönliche Daten wie Profilbild, Favoriten, Sortierungen und
				Bewertungen werden entfernt.
			</p>
			<div class="modal-actions">
				<button class="btn btn-secondary" onclick={closeDeleteDialog} disabled={savingId !== null}>
					Abbrechen
				</button>
				<button class="btn btn-danger" onclick={confirmDeletion} disabled={savingId !== null}>
					{savingId !== null ? 'Wird gelöscht …' : 'Endgültig löschen'}
				</button>
			</div>
		</Modal>
	{/if}

	{#if registrationToReject}
		<Modal title="Registrierung ablehnen?" onclose={() => (registrationToReject = null)}>
			<p class="muted">
				Das Konto „{registrationToReject.username}“ wird endgültig gelöscht. Die Person kann sich
				erneut registrieren.
			</p>
			<div class="modal-actions">
				<button class="btn btn-secondary" onclick={() => (registrationToReject = null)}>
					Abbrechen
				</button>
				<button class="btn btn-danger" onclick={confirmRejection}>Endgültig ablehnen</button>
			</div>
		</Modal>
	{/if}
{/if}

<style>
	.btn-compact {
		padding: 0.15rem 0.5rem;
		min-height: 1.75rem;
		font-size: var(--text-sm);
	}

	.user-form {
		padding: 1.5rem;
		margin-bottom: 1.5rem;
		max-width: 26rem;
		display: flex;
		flex-direction: column;
	}

	.user-table-wrap {
		overflow-x: auto;
	}

	.user-form input:disabled {
		opacity: 0.65;
	}

	.user-table {
		width: 100%;
		border-collapse: collapse;
	}

	.user-table th,
	.user-table td {
		text-align: left;
		padding: 0.6rem 1rem 0.6rem 0;
		border-bottom: 1px solid var(--color-border);
	}

	.user-table th {
		font-size: var(--text-sm);
		color: var(--color-text-muted);
		border-bottom-color: var(--color-text);
	}

	.user-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.user-actions form {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	/* On phones each user becomes a labelled block so role and actions stay in view. */
	@media (max-width: 720px) {
		.user-table thead {
			position: absolute;
			width: 1px;
			height: 1px;
			overflow: hidden;
			clip-path: inset(50%);
		}

		.user-table,
		.user-table tbody,
		.user-table tr,
		.user-table td {
			display: block;
		}

		.user-table tr {
			padding-block: 0.75rem;
			border-bottom: 1px solid var(--color-border);
		}

		.user-table td {
			display: flex;
			align-items: center;
			gap: 0.75rem;
			padding: 0.2rem 0;
			border: none;
		}

		.user-table td[data-label]::before {
			content: attr(data-label);
			flex: 0 0 5rem;
			font-size: var(--text-sm);
			color: var(--color-text-muted);
		}

		.user-name {
			font-weight: 600;
		}

		.user-actions {
			margin-top: 0.4rem;
		}
	}
</style>
