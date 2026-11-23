<script lang="ts">
	import '@fontsource-variable/fraunces/standard.css';
	import '@fontsource-variable/fraunces/standard-italic.css';
	import '@fontsource-variable/inter/standard.css';
	import '@fontsource-variable/source-serif-4/standard.css';
	import '../app.css';
	import { cookbook, defaultSettings } from '$lib/stores/settings.svelte';
	import { page } from '$app/state';
	import Header from '$lib/components/Header.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import { auth } from '$lib/stores/auth.svelte';
	import { offline } from '$lib/stores/offline.svelte';
	import { getOfflineWipeChannel, OFFLINE_WIPE_MESSAGE } from '$lib/offline/wipe-channel';
	import { installedApp } from '$lib/offline/installed';
	import { onMount, untrack } from 'svelte';

	let { children, data } = $props();
	let offlineDataRemoved = $state(false);

	auth.init();
	const checkConnection = () => void offline.probe(() => auth.user);
	$effect(() => {
		if (!installedApp() || !auth.initialized) return;
		const user = auth.user;
		untrack(() => {
			void offline.loadStatus(user, true);
			if (user) checkConnection();
		});
	});
	onMount(() => {
		try {
			offlineDataRemoved = sessionStorage.getItem(OFFLINE_WIPE_MESSAGE) === '1';
			sessionStorage.removeItem(OFFLINE_WIPE_MESSAGE);
		} catch {
			// Local data protection still works when session storage is blocked.
		}
		const handleWipe = (event: MessageEvent) => {
			if (event.data !== OFFLINE_WIPE_MESSAGE) return;
			try {
				sessionStorage.setItem(OFFLINE_WIPE_MESSAGE, '1');
			} catch {
				// Reload even when the notice cannot be stored.
			}
			window.location.reload();
		};
		const channel = getOfflineWipeChannel();
		channel?.addEventListener('message', handleWipe);
		navigator.serviceWorker?.addEventListener('message', handleWipe);
		const stopWipeNotifications = () => {
			channel?.removeEventListener('message', handleWipe);
			navigator.serviceWorker?.removeEventListener('message', handleWipe);
		};
		if (!installedApp()) return stopWipeNotifications;
		checkConnection();
		const interval = window.setInterval(checkConnection, 15000);
		const disconnected = () => offline.markConnection(true);
		window.addEventListener('online', checkConnection);
		window.addEventListener('offline', disconnected);
		window.addEventListener('focus', checkConnection);
		return () => {
			stopWipeNotifications();
			window.clearInterval(interval);
			window.removeEventListener('online', checkConnection);
			window.removeEventListener('offline', disconnected);
			window.removeEventListener('focus', checkConnection);
		};
	});
	$effect(() => {
		cookbook.settings = data.settings ?? defaultSettings;
	});
</script>

{#if !page.state.cooking}<Header />{/if}

<main class="container page">
	<div role="status">
		{#if offlineDataRemoved}
			<p class="alert">Die Offline-Daten wurden entfernt. Die App wurde neu geladen.</p>
		{/if}
	</div>
	{#if offline.offline && offline.syncError && !page.state.cooking}
		<p class="alert alert-error" role="status">Der Offline-Abgleich konnte nicht abgeschlossen werden.</p>
	{/if}
	{@render children()}
</main>

{#if !page.state.cooking}<Footer />{/if}

<style>
	.page {
		padding-block: 2rem 4rem;
		min-height: 60vh;
	}

</style>
