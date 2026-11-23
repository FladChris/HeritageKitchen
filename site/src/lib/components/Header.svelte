<script lang="ts">
	import { cookbook } from '$lib/stores/settings.svelte';
	import Icon from './Icon.svelte';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { auth } from '$lib/stores/auth.svelte';
	import { offline } from '$lib/stores/offline.svelte';
	import { installedApp, offlineImage } from '$lib/offline/installed';
	import { mayWorkOffline } from '$lib/offline/sync';
	import { goto } from '$app/navigation';

	let menuOpen = $state(false);
	let navOpen = $state(false);
	let authArea: HTMLDivElement;
	let accountButton = $state<HTMLButtonElement>();
	let navButton = $state<HTMLButtonElement>();
	let standalone = $state<boolean | null>(null);
	const syncDate = $derived(
		offline.lastCompleteSync?.userId === auth.user?.id
			? offline.lastCompleteSync?.syncedAt
			: null
	);
	const dateFormat = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium' });

	onMount(() => {
		const displayMode = window.matchMedia?.('(display-mode: standalone)');
		const updateDisplayMode = () => (standalone = installedApp());
		updateDisplayMode();
		displayMode?.addEventListener?.('change', updateDisplayMode);
		return () => displayMode?.removeEventListener?.('change', updateDisplayMode);
	});

	async function handleLogout() {
		await auth.logout();
		closeNav();
		await goto('/', { invalidateAll: true });
	}

	function isActive(path: string) {
		return page.url.pathname === path;
	}

	function closeNav() {
		menuOpen = false;
		navOpen = false;
	}

	function handleEscape(event: KeyboardEvent) {
		if (event.key !== 'Escape' || event.defaultPrevented || document.querySelector('dialog[open]')) return;
		if (menuOpen) {
			event.preventDefault();
			menuOpen = false;
			accountButton?.focus();
		} else if (navOpen) {
			event.preventDefault();
			navOpen = false;
			navButton?.focus();
		}
	}

	function handleOutsideClick(event: MouseEvent) {
		if (menuOpen && !event.composedPath().includes(authArea)) menuOpen = false;
	}

	function handleFocusOut(event: FocusEvent) {
		if (event.relatedTarget instanceof Node && !authArea.contains(event.relatedTarget)) {
			menuOpen = false;
		}
	}
</script>

<svelte:window onkeydown={handleEscape} onclick={handleOutsideClick} />

<header class="site-header">
	<div class="container header-inner">
		<div class="brand-block">
			<a class="brand" href="/" onclick={closeNav}>
				<img class="brand-mark" src="/icons/logo.svg" alt="" width="32" height="32" />
				<span class="brand-name">{cookbook.settings.cookbook_name}</span>
			</a>
			<div role="status">
				{#if standalone && offline.offline}
					<span class="offline-label">Offline-Modus</span>
					{#if offline.incomplete && mayWorkOffline(auth.user)}
						<span class="offline-label">Nicht alle Rezepte synchronisiert</span>
					{/if}
				{/if}
			</div>
			{#if standalone && !offline.offline && auth.user && mayWorkOffline(auth.user)}
				{#if offline.syncing || offline.statusUserId !== auth.user.id}
					<span class="offline-label">Wird synchronisiert …</span>
				{:else}
					<span class="offline-label">
						{#if syncDate}
							Offline verfügbar · Stand
							<time datetime={syncDate}>{dateFormat.format(new Date(syncDate))}</time>
						{:else}
							Nicht alle Rezepte synchronisiert
						{/if}
					</span>
					{#if offline.syncError}
						<span class="offline-label">{offline.syncError}</span>
					{/if}
				{/if}
			{/if}
		</div>

		<button
			class="nav-toggle"
			bind:this={navButton}
			aria-controls="primary-navigation"
			onclick={() => (navOpen ? closeNav() : (navOpen = true))}
			aria-expanded={navOpen}
			aria-label={navOpen ? 'Menü schließen' : 'Menü öffnen'}
			title={navOpen ? 'Menü schließen' : 'Menü öffnen'}
		>
			<Icon name={navOpen ? 'close' : 'menu'} />
		</button>

		<div id="primary-navigation" class="nav-collapsible" class:open={navOpen}>
			<nav class="main-nav" aria-label="Hauptnavigation">
				<a href="/" class:active={isActive('/')} onclick={closeNav}>Rezepte</a>
				{#if auth.isLoggedIn}
					<a href="/favorites" class:active={isActive('/favorites')} onclick={closeNav}>Meine Favoriten</a
					>
				{/if}
				{#if auth.hasRole('editor')}
					<a href="/recipes/new" class:active={isActive('/recipes/new')} onclick={closeNav}
						>Neues Rezept</a
					>
				{/if}
			</nav>

			<div class="auth-area" bind:this={authArea} onfocusout={handleFocusOut}>
				{#if auth.loading}
					<span class="skeleton" style="width: 90px; height: 1.6rem; display: inline-block;"></span>
				{:else if auth.user}
					<button
						class="user-chip"
						bind:this={accountButton}
						onclick={() => (menuOpen = !menuOpen)}
						aria-expanded={menuOpen}
						aria-controls="account-menu"
					>
						{#if auth.user.profile_image_path}
							<img class="user-chip-icon" src={offlineImage(auth.user.profile_image_path)} alt="" />
						{:else}
							<span class="user-chip-icon"><Icon name="user" /></span>
						{/if}
						<span class="user-chip-label">{auth.user.username}</span>
						<span class="user-chip-chevron"><Icon name="expand" /></span>
					</button>
					<div class="user-menu" id="account-menu" hidden={!menuOpen}>
						<div class="user-menu-section" role="group" aria-labelledby="account-personal">
							<div class="user-menu-label" id="account-personal">Mein Konto</div>
							<a href="/account/settings" onclick={closeNav}>
								<Icon name="settings" /> Einstellungen
							</a>
						</div>
						{#if auth.hasRole('admin')}
							<div class="user-menu-section" role="group" aria-labelledby="account-admin">
								<div class="user-menu-label" id="account-admin">Administration</div>
								<a href="/admin/settings" onclick={closeNav}>
									<Icon name="settings" /> Kochbuch-Einstellungen
								</a>
								<a href="/users" onclick={closeNav}>
									<Icon name="users" /> Benutzerverwaltung
								</a>
							</div>
						{/if}
						<div class="user-menu-section">
							<button class="logout-btn" onclick={handleLogout}
								><Icon name="logout" /> Abmelden</button
							>
						</div>
					</div>
				{:else}
					<a class="btn btn-secondary" href="/login" onclick={closeNav}>Anmelden</a>
				{/if}
			</div>
		</div>
	</div>
</header>

<style>
	.brand-block {
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.offline-label {
		display: block;
		font-family: var(--font-body);
		font-size: 0.875rem;
	}
	.site-header {
		position: sticky;
		top: 0;
		z-index: 20;
		background: var(--color-bg);
		border-bottom: 1px solid var(--color-border);
	}

	.header-inner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1.5rem;
		padding-block: 0.9rem;
	}

	.nav-toggle {
		display: none;
		flex-direction: column;
		justify-content: center;
		align-items: center;
		width: 44px;
		height: 44px;
		background: var(--color-surface-raised);
		border: 1px solid var(--color-border-input);
		border-radius: var(--radius-sm);
		flex-shrink: 0;
	}

	.nav-toggle:hover {
		background: var(--color-surface);
	}

	.nav-collapsible {
		display: flex;
		align-items: center;
		gap: 1.5rem;
		flex: 1;
		justify-content: space-between;
		min-width: 0;
	}

	.brand {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-family: var(--font-heading);
		font-weight: 600;
		font-size: var(--text-lg);
		min-height: 44px;
		min-width: 0;
		overflow-wrap: anywhere;
		color: var(--color-text);
	}

	.brand:hover {
		text-decoration: none;
		color: var(--color-text);
	}

	.brand-mark {
		flex-shrink: 0;
	}

	.main-nav {
		display: flex;
		gap: 1.25rem;
		flex-wrap: wrap;
	}

	.main-nav a {
		color: var(--color-text-muted);
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		font-weight: 600;
		font-size: var(--text-sm);
	}

	.main-nav a:hover {
		color: var(--color-text);
		text-decoration: none;
	}

	.main-nav a.active {
		color: var(--color-text);
		text-decoration: underline 2px var(--color-primary);
		text-underline-offset: 0.5em;
	}

	.auth-area {
		position: relative;
	}

	.user-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		max-width: min(16rem, calc(100vw - 2rem));
		min-height: 44px;
		background: var(--color-surface-raised);
		border: 1px solid var(--color-border-strong);
		border-radius: 999px;
		padding: 0.25rem 0.65rem 0.25rem 0.3rem;
		font-size: var(--text-sm);
		font-weight: 600;
	}

	.user-chip:hover {
		background: var(--color-surface);
	}

	.user-chip[aria-expanded='true'] {
		background: var(--color-primary);
		border-color: var(--color-primary);
		color: var(--color-primary-contrast);
	}

	.user-chip-icon,
	.user-chip-chevron {
		display: grid;
		place-items: center;
		flex-shrink: 0;
	}

	.user-chip-icon {
		width: 2rem;
		height: 2rem;
		border-radius: 50%;
		object-fit: cover;
		background: var(--color-surface);
		color: var(--color-primary);
	}

	.user-chip-chevron {
		margin-inline-start: auto;
	}

	.user-chip[aria-expanded='true'] .user-chip-chevron {
		transform: rotate(180deg);
	}

	.user-chip-label {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.user-menu {
		position: absolute;
		right: 0;
		top: calc(100% + 0.5rem);
		width: 15rem;
		max-height: calc(100dvh - 5rem);
		overflow-y: auto;
		padding: 0.375rem;
		border: 1px solid var(--color-border-strong);
		border-radius: 0.75rem;
		background: var(--color-surface-raised);
		box-shadow: 0 0.5rem 1.5rem rgb(42 33 26 / 14%);
	}

	.user-menu-section + .user-menu-section {
		margin-top: 0.25rem;
		padding-top: 0.25rem;
		border-top: 1px solid var(--color-border);
	}

	.user-menu-label {
		padding: 0.25rem 0.625rem 0;
		color: var(--color-text-muted);
		font-size: var(--text-xs);
		font-weight: 600;
	}

	.user-menu a,
	.logout-btn {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		width: 100%;
		min-height: 44px;
		text-align: left;
		padding: 0.375rem 0.625rem;
		border-radius: var(--radius-sm);
		color: var(--color-text);
		background: none;
		border: none;
		cursor: pointer;
		font-weight: 500;
		font-size: var(--text-sm);
		overflow-wrap: anywhere;
	}

	.user-menu :global(.icon) {
		flex-shrink: 0;
	}

	.user-menu :focus-visible {
		outline-offset: -3px;
	}

	.user-menu a:hover,
	.logout-btn:hover {
		background: var(--color-surface);
		text-decoration: none;
	}

	.logout-btn {
		color: var(--color-danger);
	}

	@media (max-width: 720px) {
		.site-header {
			max-height: 100dvh;
			overflow-y: auto;
		}

		.header-inner {
			display: grid;
			grid-template-columns: minmax(0, 1fr) auto;
			gap: 0.75rem 1rem;
		}

		.nav-toggle {
			display: flex;
		}

		.nav-collapsible {
			grid-column: 1 / -1;
			flex-direction: column;
			align-items: stretch;
			gap: 1rem;
			display: none;
		}

		.nav-collapsible.open {
			display: flex;
		}

		.main-nav {
			flex-direction: column;
			gap: 0.25rem;
		}

		.main-nav a {
			padding-inline: 0.25em;
		}

		.auth-area {
			width: 100%;
		}

		.user-chip {
			width: 100%;
			max-width: 100%;
		}

		.user-menu {
			position: static;
			margin-top: 0.5rem;
			width: 100%;
			max-height: none;
			box-shadow: none;
		}

		.auth-area > .btn {
			display: flex;
		}
	}

	@media (max-width: 600px) {
		.header-inner {
			padding-inline: 1rem;
		}
	}
</style>
