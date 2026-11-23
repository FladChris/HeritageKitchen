<script lang="ts">
	import { goto } from '$app/navigation';
	import * as api from '$lib/api';
	import { ApiError } from '$lib/api';
	import { loadImageFile } from '$lib/image-file';
	import Icon from '$lib/components/Icon.svelte';
	import ImageCropper from '$lib/components/ImageCropper.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import PasswordInput from '$lib/components/PasswordInput.svelte';
	import { auth } from '$lib/stores/auth.svelte';
	import { cookbook } from '$lib/stores/settings.svelte';
	import { onMount } from 'svelte';

	const imageTypes = ['image/jpeg', 'image/png'];
	const imageLimit = 20 * 1024 * 1024;
	let ready = $state(false);
	let busy = $state(false);
	let username = $state('');
	let usernameError = $state('');
	let usernameSaved = $state(false);
	let emailAvailable = $state(false);
	let emailHint = $state('');
	let email = $state('');
	let confirmEmail = $state('');
	let emailPassword = $state('');
	let emailError = $state('');
	let emailFeedback = $state('');
	let oldPassword = $state('');
	let newPassword = $state('');
	let repeatPassword = $state('');
	let passwordError = $state('');
	let passwordSaved = $state(false);
	let imageDialog = $state(false);
	let imageError = $state('');
	let removeImage = $state(false);
	let cropFile = $state<File | null>(null);
	const resending = $derived(
		email.trim() !== '' && email.trim() === auth.user?.email && !auth.user?.email_verified_at
	);

	onMount(async () => {
		await auth.init();
		if (!auth.user) {
			await goto('/login');
			return;
		}
		resetUsername();
		resetEmail();
		ready = true;
		try {
			const result = await api.emailAvailable();
			emailAvailable = result.available;
			emailHint = result.hint ?? '';
			if (emailAvailable) {
				const previous = auth.user;
				const user = await api.getCurrentUser();
				if (previous && auth.user === previous && previous.id === user.id && !busy) {
					auth.user = user;
					if (!emailPassword && email === confirmEmail && email === (previous.email ?? ''))
						resetEmail();
					if (username === previous.username) resetUsername();
				}
			}
		} catch {
			// The email form stays disabled when availability cannot be loaded.
		}
	});

	function resetUsername() {
		username = auth.user?.username ?? '';
		usernameError = '';
		usernameSaved = false;
	}

	function resetEmail() {
		email = auth.user?.email ?? '';
		confirmEmail = email;
		emailPassword = '';
		emailError = '';
		emailFeedback = '';
	}

	function resetPassword() {
		oldPassword = newPassword = repeatPassword = '';
		passwordError = '';
		passwordSaved = false;
	}

	async function saveUsername(event: SubmitEvent) {
		event.preventDefault();
		const name = username.trim();
		if (busy || name === auth.user?.username) return;
		usernameError = '';
		usernameSaved = false;
		if (name.length < 3 || name.length > 32) {
			usernameError = 'Der Benutzername muss 3–32 Zeichen lang sein.';
			return;
		}
		busy = true;
		try {
			const user = await api.updateProfile({ username: name });
			if (auth.user?.id !== user.id) return;
			auth.user = user;
			username = user.username;
			usernameSaved = true;
		} catch (error) {
			usernameError =
				error instanceof ApiError
					? error.message
					: 'Der Benutzername konnte nicht geändert werden.';
		} finally {
			busy = false;
		}
	}

	function submitEmail(event: SubmitEvent) {
		event.preventDefault();
		if (!emailAvailable || busy) return;
		const address = email.trim();
		if (address.toLowerCase() !== confirmEmail.trim().toLowerCase()) {
			emailFeedback = '';
			emailError = 'Die E-Mail-Adressen stimmen nicht überein.';
			return;
		}
		void saveEmail(address || null);
	}

	async function saveEmail(address: string | null) {
		if (busy) return;
		emailError = emailFeedback = '';
		if (!emailPassword) {
			emailError = 'Gib dein aktuelles Passwort ein.';
			return;
		}
		busy = true;
		try {
			const user = await api.updateProfile({
				email: address,
				current_password: emailPassword
			});
			if (auth.user?.id !== user.id) return;
			auth.user = user;
			resetEmail();
			emailFeedback = user.email
				? 'Der Bestätigungslink wurde angefordert. Prüfe dein Postfach.'
				: 'Deine E-Mail-Adresse wurde entfernt.';
		} catch (error) {
			emailError =
				error instanceof ApiError
					? error.message
					: 'Die E-Mail-Adresse konnte nicht geändert werden.';
		} finally {
			busy = false;
		}
	}

	async function savePassword(event: SubmitEvent) {
		event.preventDefault();
		if (busy) return;
		passwordError = '';
		passwordSaved = false;
		if (newPassword.length < 8) {
			passwordError = 'Das neue Passwort muss mindestens 8 Zeichen lang sein.';
			return;
		}
		if (newPassword !== repeatPassword) {
			passwordError = 'Die neuen Passwörter stimmen nicht überein.';
			return;
		}
		busy = true;
		try {
			await api.changePassword(oldPassword, newPassword);
			resetPassword();
			passwordSaved = true;
		} catch (error) {
			passwordError =
				error instanceof ApiError
					? error.message === 'Current password is incorrect.'
						? 'Das aktuelle Passwort ist falsch.'
						: error.message === 'New password must differ from current password.'
							? 'Das neue Passwort muss sich vom aktuellen unterscheiden.'
							: error.message
					: 'Das Passwort konnte nicht geändert werden.';
		} finally {
			busy = false;
		}
	}

	function openImageDialog() {
		imageError = '';
		removeImage = false;
		cropFile = null;
		imageDialog = true;
	}

	function closeImageDialog() {
		if (!busy) imageDialog = false;
	}

	async function prepareImage(file: File) {
		if (!imageTypes.includes(file.type)) {
			imageError = 'Erlaubt sind JPG und PNG.';
			return;
		}
		if (file.size > imageLimit) {
			imageError = 'Das Bild darf höchstens 20 MB groß sein.';
			return;
		}
		const url = URL.createObjectURL(file);
		try {
			const image = new Image();
			image.src = url;
			await image.decode();
			if (image.naturalWidth < 200 || image.naturalHeight < 200) {
				imageError = 'Das Bild muss mindestens 200 × 200 Pixel groß sein.';
				return;
			}
			removeImage = false;
			cropFile = file;
		} catch {
			imageError = 'Das Bild konnte nicht geöffnet werden.';
		} finally {
			URL.revokeObjectURL(url);
		}
	}

	async function chooseImage(file?: File) {
		if (!file || busy) return;
		busy = true;
		imageError = '';
		try {
			await prepareImage(file);
		} finally {
			busy = false;
		}
	}

	function onFileChange(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		void chooseImage(file);
	}

	async function editExistingImage(path: string) {
		if (busy) return;
		busy = true;
		imageError = '';
		try {
			await prepareImage(await loadImageFile(path, 'profilbild.jpg'));
		} catch {
			imageError = 'Dein Profilbild konnte nicht geladen werden.';
		} finally {
			busy = false;
		}
	}

	async function saveImage(file?: File) {
		if (!imageDialog || busy || (!file && !removeImage)) return;
		busy = true;
		imageError = '';
		try {
			const user = await (file ? api.setProfileImage(file) : api.removeProfileImage());
			if (auth.user?.id === user.id) auth.user = user;
			imageDialog = false;
		} catch (error) {
			imageError =
				error instanceof ApiError ? error.message : 'Dein Profilbild konnte nicht geändert werden.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head>
	<title>Einstellungen &middot; {cookbook.settings.cookbook_name}</title>
</svelte:head>

{#if ready && auth.user}
	<div class="settings-page">
		<h1>Einstellungen</h1>
		<form class="card username-card" onsubmit={saveUsername}>
			<div class="avatar-wrap">
				{#if auth.user.profile_image_path}
					<img
						class="avatar"
						src={auth.user.profile_image_path}
						alt="Dein Profilbild"
						width="96"
						height="96"
					/>
				{:else}
					<span class="avatar" aria-hidden="true"
						>{Array.from(auth.user.username)[0]?.toUpperCase()}</span
					>
				{/if}
				<button
					class="icon-btn avatar-edit"
					type="button"
					aria-label="Profilbild bearbeiten"
					title="Profilbild bearbeiten"
					onclick={openImageDialog}
					disabled={busy}
				>
					<Icon name="edit" />
				</button>
			</div>
			<div class="username-field">
				<h2>Username ändern</h2>
				<p id="username-hint" class="muted">
					3–32 Zeichen. Dein Benutzername wird auch bei deinen Beiträgen angezeigt.
				</p>
				{#if usernameError}<p class="alert alert-error" role="alert">{usernameError}</p>{/if}
				{#if usernameSaved}<p class="alert alert-success" role="status">
						Dein Benutzername wurde geändert.
					</p>{/if}
				<div class="field">
					<label for="profile-username">Benutzername</label>
					<input
						id="profile-username"
						bind:value={username}
						autocomplete="username"
						minlength={3}
						maxlength={32}
						required
						disabled={busy}
						aria-describedby="username-hint"
					/>
				</div>
			</div>
			<div class="settings-actions">
				<button class="btn btn-secondary" type="button" onclick={resetUsername} disabled={busy}
					>Abbrechen</button
				>
				<button
					class="btn btn-primary"
					type="submit"
					disabled={busy || username.trim() === auth.user.username}>Username ändern</button
				>
			</div>
		</form>

		<form class="card" onsubmit={submitEmail}>
			<h2>E-Mail ändern</h2>
			<p class="muted">
				Bestätige die neue Adresse über den Link in deinem Postfach. Sobald du die Änderung
				speicherst, endet die Anmeldung mit der bisherigen E-Mail-Adresse.
			</p>
			{#if auth.user.email}
				<p class="muted">
					{emailAvailable && auth.user.email_verified_at ? 'Bestätigt' : 'Unbestätigt'} · {auth.user
						.email}
				</p>
			{/if}
			{#if !emailAvailable}
				<p id="mail-disabled" class="muted">
					{emailHint || 'E-Mail ist erst verfügbar, wenn SMTP eingerichtet und getestet ist.'}
				</p>
			{/if}
			{#if emailError}<p class="alert alert-error" role="alert">{emailError}</p>{/if}
			{#if emailFeedback}<p class="alert alert-success" role="status">{emailFeedback}</p>{/if}
			<div class="field-pair">
				<div class="field">
					<label for="profile-email">E-Mail</label>
					<input
						id="profile-email"
						type="email"
						bind:value={email}
						autocomplete="email"
						disabled={!emailAvailable || busy}
						aria-describedby={!emailAvailable ? 'mail-disabled' : undefined}
					/>
				</div>
				<div class="field">
					<label for="confirm-email">E-Mail bestätigen</label>
					<input
						id="confirm-email"
						type="email"
						bind:value={confirmEmail}
						autocomplete="off"
						disabled={!emailAvailable || busy}
						aria-describedby={!emailAvailable ? 'mail-disabled' : undefined}
					/>
				</div>
			</div>
			<div class="field">
				<label for="email-password">Passwort zur Identifizierung</label>
				<PasswordInput
					id="email-password"
					bind:value={emailPassword}
					autocomplete="current-password"
					required
					disabled={busy || (!emailAvailable && !auth.user.email)}
				/>
			</div>
			<div class="settings-actions">
				<button
					class="btn btn-secondary"
					type="button"
					onclick={resetEmail}
					disabled={busy || (!emailAvailable && !auth.user.email)}>Abbrechen</button
				>
				{#if auth.user.email}
					<button
						class="btn btn-secondary"
						type="button"
						onclick={() => saveEmail(null)}
						disabled={busy}>E-Mail entfernen</button
					>
				{/if}
				<button
					class="btn btn-primary"
					type="submit"
					disabled={!emailAvailable ||
						busy ||
						(!resending && email.trim() === (auth.user.email ?? ''))}
				>
					{resending ? 'Bestätigungslink erneut senden' : 'E-Mail ändern'}
				</button>
			</div>
		</form>

		<form class="card" onsubmit={savePassword}>
			<h2>Passwort ändern</h2>
			<p class="muted">
				Deine aktuelle Sitzung bleibt bestehen. Andere Sitzungen werden beendet und offene
				Passwort-Reset-Links werden ungültig.
			</p>
			{#if passwordError}<p class="alert alert-error" role="alert">{passwordError}</p>{/if}
			{#if passwordSaved}<p class="alert alert-success" role="status">
					Dein Passwort wurde geändert.
				</p>{/if}
			<div class="field">
				<label for="old-password">Altes Passwort</label>
				<PasswordInput
					id="old-password"
					bind:value={oldPassword}
					autocomplete="current-password"
					required
					disabled={busy}
				/>
			</div>
			<div class="field-pair">
				<div class="field">
					<label for="new-password">Neues Passwort</label>
					<PasswordInput
						id="new-password"
						bind:value={newPassword}
						autocomplete="new-password"
						required
						minlength={8}
						disabled={busy}
					/>
				</div>
				<div class="field">
					<label for="repeat-password">Neues Passwort wiederholen</label>
					<PasswordInput
						id="repeat-password"
						bind:value={repeatPassword}
						autocomplete="new-password"
						required
						minlength={8}
						disabled={busy}
					/>
				</div>
			</div>
			<div class="settings-actions">
				<button class="btn btn-secondary" type="button" onclick={resetPassword} disabled={busy}
					>Abbrechen</button
				>
				<button class="btn btn-primary" type="submit" disabled={busy}>Passwort ändern</button>
			</div>
		</form>
	</div>

	{#if imageDialog}
		<Modal title="Profilbild" onclose={closeImageDialog}>
			<p class="muted">
				Erlaubt sind JPG und PNG ab 200 × 200 Pixel und bis 20 MB. Das Bild wird quadratisch
				zugeschnitten.
			</p>
			{#if imageError}<p class="alert alert-error" role="alert">{imageError}</p>{/if}
			{#if cropFile}
				{#key cropFile}
					<ImageCropper
						file={cropFile}
						aspect={1}
						allowAspectChoice={false}
						embedded
						minSize={200}
						saveLabel="Speichern"
						disabled={busy}
						onDone={saveImage}
						onCancel={closeImageDialog}
					/>
				{/key}
			{:else}
				<label
					class="drop-area"
					class:disabled={busy}
					ondragover={(event) => event.preventDefault()}
					ondrop={(event) => {
						event.preventDefault();
						void chooseImage(event.dataTransfer?.files[0]);
					}}
				>
					<Icon name="plus" /> Bild hinzufügen
					<input
						class="sr-only"
						type="file"
						accept={imageTypes.join(',')}
						onchange={onFileChange}
						disabled={busy}
					/>
				</label>
				<div class="image-tools">
					<label class="btn btn-secondary camera" class:disabled={busy}>
						<Icon name="camera" /> Foto aufnehmen
						<input
							class="sr-only"
							type="file"
							accept={imageTypes.join(',')}
							capture="user"
							onchange={onFileChange}
							disabled={busy}
						/>
					</label>
					{#if auth.user.profile_image_path && !removeImage}
						{@const path = auth.user.profile_image_path}
						<button
							class="btn btn-secondary"
							type="button"
							onclick={() => editExistingImage(path)}
							disabled={busy}>Bild zuschneiden</button
						>
						<button
							class="btn btn-secondary"
							type="button"
							onclick={() => (removeImage = true)}
							disabled={busy}>Bild entfernen</button
						>
					{:else if removeImage}
						<p class="muted" role="status">Das Profilbild wird beim Speichern entfernt.</p>
					{/if}
				</div>
				<div class="modal-actions">
					<button class="btn btn-secondary" type="button" onclick={closeImageDialog} disabled={busy}
						>Abbrechen</button
					>
					<button
						class="btn btn-primary"
						type="button"
						onclick={() => saveImage()}
						disabled={busy || !removeImage}>Speichern</button
					>
				</div>
			{/if}
		</Modal>
	{/if}
{/if}

<style>
	.username-card {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		gap: 0 1.5rem;
		align-items: start;
	}

	.username-card .settings-actions {
		grid-column: 1 / -1;
	}
	.username-field {
		min-width: 0;
	}

	.avatar-wrap {
		position: relative;
	}

	.avatar {
		display: grid;
		width: 96px;
		height: 96px;
		place-items: center;
		border-radius: 50%;
		object-fit: cover;
		background: var(--color-surface-raised);
		border: 1px solid var(--color-border-strong);
		font-size: 2rem;
	}

	.avatar-edit {
		position: absolute;
		right: -0.375rem;
		bottom: -0.375rem;
		border: 1px solid var(--color-border-strong);
		border-radius: 50%;
		background: var(--color-surface-raised);
	}

	.field input:disabled,
	label.disabled {
		opacity: 0.65;
	}

	.image-tools {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-top: 0.75rem;
	}

	.drop-area {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		min-height: 5rem;
		border: 1px dashed var(--color-border-strong);
		border-radius: var(--radius-sm);
		cursor: pointer;
	}

	label:focus-within {
		outline: 2px solid var(--color-primary);
		outline-offset: 2px;
	}

	.camera {
		display: none;
	}
	@media (pointer: coarse) {
		.camera {
			display: inline-flex;
		}
	}
	@media (max-width: 32rem) {
		.username-card {
			column-gap: 1rem;
		}
		.avatar {
			width: 60px;
			height: 60px;
			font-size: 1.5rem;
		}
	}
</style>
