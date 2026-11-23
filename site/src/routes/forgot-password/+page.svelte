<script lang="ts">
	import { cookbook } from '$lib/stores/settings.svelte';
	import { onMount } from 'svelte';
	import * as api from '$lib/api';
	let available = $state(false);
	let email = $state('');
	let requested = $state(false);
	let submitting = $state(false);
	let error = $state('');
	onMount(async () => {
		try {
			available = (await api.resetAvailable()).available;
		} catch {
			available = false;
		}
	});
	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (submitting) return;
		submitting = true;
		error = '';
		try {
			await api.requestPasswordReset(email);
			requested = true;
		} catch {
			error = 'Anfrage fehlgeschlagen. Bitte versuche es später erneut.';
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head><title>Passwort vergessen · {cookbook.settings.cookbook_name}</title></svelte:head>
<div class="narrow-page">
	<div class="card">
		<h1>Passwort vergessen</h1>
		{#if !available}<p>Bitte wende dich an einen Admin.</p>
		{:else if requested}<p role="status">Deine Anfrage wurde entgegengenommen.</p>
		{:else}
			<p>Gib deine hinterlegte E-Mail-Adresse ein.</p>
			{#if error}<p class="alert alert-error" role="alert">{error}</p>{/if}
			<form onsubmit={submit}>
				<div class="field">
					<label for="email">E-Mail</label>
					<input id="email" type="email" bind:value={email} required />
				</div>
				<button class="btn btn-primary" type="submit" disabled={submitting}>Link anfordern</button>
			</form>
		{/if}
	</div>
</div>
