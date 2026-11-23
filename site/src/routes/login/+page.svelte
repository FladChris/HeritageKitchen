<script lang="ts">
	import { cookbook } from '$lib/stores/settings.svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { auth } from '$lib/stores/auth.svelte';
	import { ApiError } from '$lib/api';
	import * as api from '$lib/api';
	import { onMount } from 'svelte';
	import PasswordInput from '$lib/components/PasswordInput.svelte';

	let identifier = $state('');
	let password = $state('');
	let error = $state<string | null>(null);
	let submitting = $state(false);
	let resetAvailable = $state(false);
	onMount(async () => {
		try {
			resetAvailable = (await api.resetAvailable()).available;
		} catch {
			/* Login bleibt nutzbar. */
		}
	});

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		error = null;
		submitting = true;
		try {
			await auth.login(identifier, password);
			await goto('/', { invalidateAll: true });
		} catch (err) {
			error =
				err instanceof ApiError
					? err.status === 401
						? 'Anmeldekennung oder Passwort ist falsch.'
						: err.message
					: 'Anmeldung fehlgeschlagen.';
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head>
	<title>Anmelden &middot; {cookbook.settings.cookbook_name}</title>
</svelte:head>

<div class="narrow-page">
	<form class="card" onsubmit={handleSubmit}>
		<h1>Willkommen zurück</h1>
		<p class="muted">Melde dich an, um deine Kontofunktionen zu nutzen.</p>

		{#if error}
			<p class="alert alert-error" role="alert">{error}</p>
		{:else if page.url.searchParams.get('registered') === 'pending'}
			<p class="alert alert-success" role="status">
				Konto erstellt. Dein Konto muss von einem Administrator freigeschaltet werden.
			</p>
		{:else if page.url.searchParams.get('registered') === '1'}
			<p class="alert alert-success">Konto erstellt &ndash; du kannst dich jetzt anmelden.</p>
		{/if}
		{#if page.url.searchParams.get('confirmEmail') === '1'}
			<p class="muted">Bestätige deine E-Mail-Adresse über den Link in deinem Postfach.</p>
		{/if}

		<div class="field">
			<label for="username"
				>{resetAvailable ? 'Benutzername oder E-Mail-Adresse' : 'Benutzername'}</label
			>
			<input id="username" type="text" bind:value={identifier} autocomplete="username" required />
		</div>

		<div class="field">
			<label for="password">Passwort</label>
			<PasswordInput id="password" bind:value={password} autocomplete="current-password" required />
		</div>

		<button class="btn btn-primary" type="submit" disabled={submitting}>
			{submitting ? 'Melde an …' : 'Anmelden'}
		</button>
		{#if resetAvailable}
			<p class="muted form-hint"><a href="/forgot-password">Passwort vergessen?</a></p>
		{:else}
			<p class="muted form-hint">Passwort vergessen? Bitte wende dich an einen Admin.</p>
		{/if}

		<p class="muted form-hint">
			Noch kein Konto? <a href="/register">Jetzt registrieren</a>
		</p>
	</form>
</div>
