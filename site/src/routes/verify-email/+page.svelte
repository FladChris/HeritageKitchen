<script lang="ts">
	import { page } from '$app/state';
	import { ApiError, verifyEmail } from '$lib/api';
	import { auth } from '$lib/stores/auth.svelte';
	import { cookbook } from '$lib/stores/settings.svelte';

	const token = $derived(page.url.searchParams.get('token'));
	let busy = $state(false);
	let done = $state(false);
	let error = $state('');

	async function confirm() {
		if (!token || busy) return;
		busy = true;
		error = '';
		try {
			await verifyEmail(token);
			done = true;
			if (auth.user) void auth.refresh();
		} catch (err) {
			error =
				err instanceof ApiError ? err.message : 'Die E-Mail-Adresse konnte nicht bestätigt werden.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head>
	<title>E-Mail bestätigen · {cookbook.settings.cookbook_name}</title>
	<meta name="referrer" content="no-referrer" />
</svelte:head>

<div class="narrow-page">
	<div class="card">
		<h1>E-Mail bestätigen</h1>
		{#if done}
			<p class="alert alert-success" role="status">Deine E-Mail-Adresse wurde bestätigt.</p>
			{#if auth.user}
				<a href="/account/settings">Zu den Kontoeinstellungen</a>
			{:else}
				<a href="/login">Zur Anmeldung</a>
			{/if}
		{:else if token}
			{#if error}<p class="alert alert-error" role="alert">{error}</p>{/if}
			<button class="btn btn-primary" type="button" onclick={confirm} disabled={busy}>
				{busy ? 'Wird bestätigt …' : 'E-Mail bestätigen'}
			</button>
		{:else}
			<p role="alert">Der Bestätigungslink ist ungültig.</p>
		{/if}
	</div>
</div>
