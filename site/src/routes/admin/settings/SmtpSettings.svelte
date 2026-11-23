<script lang="ts">
	import { onMount } from 'svelte';
	import * as api from '$lib/api';
	import Modal from '$lib/components/Modal.svelte';
	import PasswordInput from '$lib/components/PasswordInput.svelte';
	import type { SmtpSettings } from '$lib/types';

	const statusText = {
		not_configured: 'Nicht eingerichtet',
		untested: 'Eingerichtet, noch nicht erfolgreich getestet',
		tested: 'Erfolgreich getestet'
	};
	const providers = {
		gmail: { label: 'Gmail', host: 'smtp.gmail.com', domain: 'gmail.com' },
		gmx: { label: 'GMX', host: 'mail.gmx.net', domain: 'gmx.de' },
		webde: { label: 'WEB.DE', host: 'smtp.web.de', domain: 'web.de' }
	};
	type Provider = keyof typeof providers | 'custom';

	let settings = $state<SmtpSettings | null>(null);
	let settingsForm = $state<HTMLFormElement>();
	let provider = $state<Provider>('custom');
	let host = $state('');
	let port = $state<number | undefined>(587);
	let encryption = $state<SmtpSettings['encryption']>('starttls');
	let username = $state('');
	let password = $state('');
	let sender = $state('');
	let senderFollowsUsername = $state(true);
	let recipient = $state('');
	let pending = $state(false);
	let error = $state('');
	let feedback = $state('');
	let confirmingRemoval = $state(false);
	const domain = $derived(provider === 'custom' ? 'example.com' : providers[provider].domain);

	function apply(result: SmtpSettings) {
		settings = result;
		({ host, port, encryption, username, sender } = result);
		password = '';
		senderFollowsUsername = sender === username;
	}

	function selectProvider(value: Provider) {
		provider = value;
		if (value !== 'custom') {
			host = providers[value].host;
			port = 587;
			encryption = 'starttls';
		}
	}

	function updateUsername(value: string) {
		username = value;
		if (senderFollowsUsername) sender = value;
	}

	function draftSettings() {
		if (!settings || port === undefined) return;
		return { version: settings.version, host, port, encryption, username, password, sender };
	}

	onMount(async () => {
		try {
			apply(await api.getSmtpSettings());
			provider =
				(Object.keys(providers) as (keyof typeof providers)[]).find(
					(key) => providers[key].host === host.toLowerCase()
				) ?? 'custom';
		} catch {
			error = 'SMTP-Einstellungen konnten nicht geladen werden.';
		}
	});

	async function save(event: SubmitEvent) {
		event.preventDefault();
		const draft = draftSettings();
		if (pending || !draft) return;
		pending = true;
		error = feedback = '';
		try {
			apply(await api.updateSmtpSettings(draft));
			feedback = 'SMTP-Einstellungen gespeichert.';
		} catch (err) {
			error =
				err instanceof api.ApiError
					? err.message
					: 'SMTP-Einstellungen konnten nicht gespeichert werden.';
		} finally {
			pending = false;
		}
	}

	async function sendTest(event: SubmitEvent) {
		event.preventDefault();
		if (pending || !settingsForm?.reportValidity()) return;
		const draft = draftSettings();
		if (!draft) return;
		pending = true;
		error = feedback = '';
		try {
			await api.sendSmtpTest(recipient, draft);
			feedback =
				'Der SMTP-Server hat die Test-E-Mail angenommen. Speichere die getesteten Einstellungen.';
		} catch (err) {
			error =
				err instanceof api.ApiError ? err.message : 'Die Test-E-Mail konnte nicht gesendet werden.';
		} finally {
			pending = false;
		}
	}

	async function removeSettings() {
		if (pending || !settings) return;
		pending = true;
		error = feedback = '';
		try {
			apply(
				await api.updateSmtpSettings({
					version: settings.version,
					host: '',
					sender: '',
					port: 587,
					encryption: 'starttls',
					username: '',
					password: ''
				})
			);
			provider = 'custom';
			feedback = 'Die SMTP-Einstellungen wurden entfernt.';
		} catch (err) {
			error = err instanceof api.ApiError ? err.message : 'SMTP konnte nicht entfernt werden.';
		} finally {
			pending = confirmingRemoval = false;
		}
	}
</script>

<section class="card" aria-labelledby="smtp-heading">
	<h2 id="smtp-heading">SMTP-Versand</h2>
	{#if error}<p class="alert alert-error" role="alert">{error}</p>{/if}
	{#if settings}
		<p role="status">{statusText[settings.status]}</p>
		{#if settings.account_mail_hint}<p class="muted">{settings.account_mail_hint}</p>{/if}
		{#if feedback}<p class="alert alert-success" role="status">{feedback}</p>{/if}
		<form bind:this={settingsForm} onsubmit={save} oninput={() => (feedback = '')}>
			<fieldset disabled={pending}>
				<div class="field">
					<label for="smtp-provider">Anbieter</label>
					<select
						id="smtp-provider"
						value={provider}
						aria-describedby={provider === 'custom' ? undefined : 'smtp-provider-hint'}
						onchange={(event) => selectProvider(event.currentTarget.value as Provider)}
					>
						{#each Object.entries(providers) as [key, preset] (key)}
							<option value={key}>{preset.label}</option>
						{/each}
						<option value="custom">Eigener Server</option>
					</select>
					{#if provider === 'gmail'}
						<span id="smtp-provider-hint" class="muted"
							>Gmail benötigt ein <a href="https://myaccount.google.com/apppasswords"
								>App-Passwort</a
							>.</span
						>
					{:else if provider === 'gmx' || provider === 'webde'}
						<span id="smtp-provider-hint" class="muted">
							Aktiviere im Postfach „POP3/IMAP-Zugriff erlauben“.
						</span>
					{/if}
				</div>
				<div class="field smtp-host">
					<label for="smtp-host">SMTP-Server</label>
					<input
						id="smtp-host"
						bind:value={host}
						oninput={() => (provider = 'custom')}
						placeholder="smtp.example.com"
						maxlength="253"
						required
					/>
				</div>
				<div class="field smtp-port">
					<label for="smtp-port">Port</label>
					<input
						id="smtp-port"
						type="number"
						bind:value={port}
						oninput={() => (provider = 'custom')}
						min="1"
						max="65535"
						required
					/>
				</div>
				<div class="field smtp-encryption">
					<label for="smtp-encryption">Verschlüsselung</label>
					<select
						id="smtp-encryption"
						bind:value={encryption}
						onchange={() => (provider = 'custom')}
					>
						<option value="starttls">STARTTLS</option>
						<option value="tls">TLS</option>
						<option value="none">Keine</option>
					</select>
				</div>
				<div class="field smtp-credentials">
					<label for="smtp-username">SMTP-Benutzername (optional)</label>
					<input
						id="smtp-username"
						value={username}
						oninput={(event) => updateUsername(event.currentTarget.value)}
						placeholder={`name@${domain}`}
						maxlength="320"
						autocomplete="off"
					/>
				</div>
				<div class="field smtp-credentials">
					<label for="smtp-password">SMTP-Passwort</label>
					<PasswordInput
						id="smtp-password"
						bind:value={password}
						placeholder={provider === 'gmail' ? 'App-Passwort' : 'SMTP-Passwort'}
						maxlength={4096}
						autocomplete="new-password"
						aria-describedby="smtp-password-hint"
					/>
					<span id="smtp-password-hint" class="muted">
						{settings.has_password
							? 'Leer lassen, um das gespeicherte Passwort zu behalten.'
							: 'Gib ein Passwort ein, wenn dein SMTP-Server eines verlangt.'}
					</span>
				</div>
				<div class="field">
					<label for="smtp-sender">Absenderadresse</label>
					<input
						id="smtp-sender"
						type="email"
						bind:value={sender}
						oninput={(event) => {
							if (event.currentTarget.value !== username) senderFollowsUsername = false;
						}}
						placeholder={`name@${domain}`}
						aria-describedby={provider === 'custom' ? undefined : 'smtp-sender-hint'}
						required
					/>
					{#if provider !== 'custom'}
						<span id="smtp-sender-hint" class="muted">
							{providers[provider].label} akzeptiert als Absender nur die eigene E-Mail-Adresse.
						</span>
					{/if}
				</div>
				<div class="settings-actions">
					{#if settings.status !== 'not_configured'}
						<button
							class="btn btn-secondary"
							type="button"
							onclick={() => (confirmingRemoval = true)}
						>SMTP-Einstellungen entfernen</button>
					{/if}
					<button class="btn btn-primary" type="submit">SMTP-Einstellungen speichern</button>
				</div>
			</fieldset>
		</form>
		<form class="smtp-test" aria-labelledby="smtp-test-heading" onsubmit={sendTest}>
			<h3 id="smtp-test-heading">Testversand</h3>
			<p class="muted" id="smtp-test-hint">
				Prüfe die eingetragenen SMTP-Einstellungen vor dem Speichern mit einer Test-E-Mail.
			</p>
			<div class="smtp-test-row">
				<div class="field">
					<label for="smtp-recipient">Empfängeradresse</label>
					<input
						id="smtp-recipient"
						type="email"
						bind:value={recipient}
						disabled={pending}
						aria-describedby="smtp-test-hint"
						required
					/>
				</div>
				<button class="btn btn-secondary" type="submit" disabled={pending}>Test-E-Mail senden</button>
			</div>
		</form>
	{:else if !error}
		<p role="status">SMTP-Einstellungen werden geladen …</p>
	{/if}
</section>

{#if confirmingRemoval}
	<Modal
		title="SMTP-Einstellungen entfernen?"
		onclose={() => {
			if (!pending) confirmingRemoval = false;
		}}
	>
		<p class="muted">
			Die gespeicherten E-Mail-Adressen müssen nach erneuter Einrichtung bestätigt werden.
		</p>
		<div class="modal-actions">
			<button
				class="btn btn-secondary"
				disabled={pending}
				onclick={() => (confirmingRemoval = false)}>Abbrechen</button
			>
			<button class="btn btn-danger" disabled={pending} onclick={removeSettings}>Entfernen</button>
		</div>
	</Modal>
{/if}

<style>
	fieldset {
		border: 0;
		margin: 0;
		padding: 0;
		min-width: 0;
	}
	.smtp-port input {
		width: 100%;
	}
	.smtp-test {
		margin-top: 1.5rem;
		padding: clamp(1rem, 2vw, 1.5rem);
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
	}
	.smtp-test-row {
		display: grid;
		gap: 0.75rem 1.25rem;
	}
	.smtp-test-row .field {
		margin: 0;
	}
	@media (width > 40rem) {
		.smtp-test-row {
			grid-template-columns: minmax(0, 1fr) auto;
			align-items: end;
		}
	}
	@media (min-width: 44rem) {
		fieldset {
			display: grid;
			grid-template-columns: repeat(6, minmax(0, 1fr));
			column-gap: 1.25rem;
		}
		fieldset > * {
			grid-column: 1 / -1;
		}
		.smtp-host,
		.smtp-credentials {
			grid-column: span 3;
		}
		.smtp-port {
			grid-column: span 1;
		}
		.smtp-encryption {
			grid-column: span 2;
		}
	}
</style>
