<script lang="ts">
	import { cookbook } from '$lib/stores/settings.svelte';
	import { page } from '$app/state';
	import * as api from '$lib/api';
	import PasswordInput from '$lib/components/PasswordInput.svelte';
	let password = $state('');
	let repeat = $state('');
	let done = $state(false);
	let error = $state('');
	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (password !== repeat) {
			error = 'Die Passwörter stimmen nicht überein.';
			return;
		}
		try {
			await api.resetPassword(page.url.searchParams.get('token') ?? '', password);
			done = true;
		} catch {
			error = 'Der Link ist ungültig oder abgelaufen.';
		}
	}
</script>

<svelte:head><title>Passwort zurücksetzen · {cookbook.settings.cookbook_name}</title></svelte:head>
<div class="narrow-page">
	<div class="card">
		<h1>Passwort zurücksetzen</h1>
		{#if done}<p>Passwort geändert. <a href="/login">Jetzt anmelden</a></p>
		{:else if !page.url.searchParams.get('token')}<p>Der Link ist ungültig.</p>
		{:else}
			{#if error}<p class="alert alert-error">{error}</p>{/if}
			<form onsubmit={submit}>
				<div class="field">
					<label for="password">Neues Passwort</label><PasswordInput
						id="password"
						bind:value={password}
						minlength={8}
						required
					/>
				</div>
				<div class="field">
					<label for="repeat">Passwort wiederholen</label><PasswordInput
						id="repeat"
						bind:value={repeat}
						minlength={8}
						required
					/>
				</div>
				<button class="btn btn-primary" type="submit">Passwort setzen</button>
			</form>
		{/if}
	</div>
</div>
