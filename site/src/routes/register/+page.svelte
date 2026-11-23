<script lang="ts">
	import { cookbook } from '$lib/stores/settings.svelte';
	import { goto } from '$app/navigation';
	import * as api from '$lib/api';
	import { ApiError } from '$lib/api';
	import PasswordInput from '$lib/components/PasswordInput.svelte';
	import { onMount } from 'svelte';

	let username = $state('');
	let email = $state('');
	let emailAvailable = $state(false);
	let emailHint = $state('');
	let password = $state('');
	let error = $state<string | null>(null);
	let submitting = $state(false);
	let firstAccount = $state<boolean | null>(null);
	let statusFailed = $state(false);

	async function loadRegistrationStatus() {
		statusFailed = false;
		try {
			firstAccount = (await api.registrationStatus()).first_account;
		} catch {
			statusFailed = true;
		}
	}

	onMount(() => {
		void loadRegistrationStatus();
		void api.emailAvailable().then(
			(result) => {
				emailAvailable = result.available;
				emailHint = result.hint ?? '';
			},
			() => (emailAvailable = false)
		);
	});

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (firstAccount === null || submitting) return;
		error = null;
		submitting = true;
		try {
			const user = await api.register({
				username,
				email: emailAvailable ? email.trim() || null : null,
				password
			});
			const registered = user.pending_approval ? 'pending' : '1';
			goto(`/login?registered=${registered}${user.email ? '&confirmEmail=1' : ''}`);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Registrierung fehlgeschlagen.';
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head>
	<title>Registrieren &middot; {cookbook.settings.cookbook_name}</title>
</svelte:head>

<div class="narrow-page">
	<form class="card" onsubmit={handleSubmit}>
		<h1>Konto erstellen</h1>
		{#if firstAccount === true}
			<p class="muted">Das erste Konto erhält automatisch die Rolle „Administrator“.</p>
		{:else if firstAccount === false}
			<p class="muted">Dein Konto muss von einem Administrator freigeschaltet werden.</p>
		{:else if statusFailed}
			<p class="alert alert-error" role="alert">
				Registrierungsstatus konnte nicht geladen werden.
			</p>
			<button class="btn btn-secondary" type="button" onclick={loadRegistrationStatus}>
				Erneut versuchen
			</button>
		{:else}
			<p class="muted" role="status">Registrierungsstatus wird geladen …</p>
		{/if}

		{#if error}
			<p class="alert alert-error">{error}</p>
		{/if}

		<div class="field">
			<label for="username">Benutzername</label>
			<input
				id="username"
				type="text"
				bind:value={username}
				autocomplete="username"
				minlength={3}
				maxlength={32}
				required
			/>
		</div>

		<div class="field">
			<label for="email">E-Mail (optional)</label>
			<input
				id="email"
				type="email"
				bind:value={email}
				autocomplete="email"
				disabled={!emailAvailable || submitting}
				aria-describedby="email-hint"
			/>
			<small class="muted" id="email-hint">
				{emailAvailable
					? 'Bestätige deine Adresse per E-Mail, um sie für Anmeldung und Passwort-Reset zu nutzen.'
					: emailHint || 'E-Mail ist erst verfügbar, wenn SMTP eingerichtet und getestet ist.'}
			</small>
		</div>

		<div class="field">
			<label for="password">Passwort</label>
			<PasswordInput
				id="password"
				bind:value={password}
				autocomplete="new-password"
				minlength={8}
				required
			/>
		</div>

		<button class="btn btn-primary" type="submit" disabled={firstAccount === null || submitting}>
			{submitting ? 'Erstelle Konto …' : 'Konto erstellen'}
		</button>

		<p class="muted form-hint">
			Schon ein Konto? <a href="/login">Jetzt anmelden</a>
		</p>
	</form>
</div>

<style>
	input:disabled {
		opacity: 0.65;
	}
</style>
