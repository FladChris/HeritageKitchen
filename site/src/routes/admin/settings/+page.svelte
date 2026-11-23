<script lang="ts">
	import { downloadBlob } from '$lib/download';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import * as api from '$lib/api';
	import { auth } from '$lib/stores/auth.svelte';
	import { cookbook } from '$lib/stores/settings.svelte';
	import SmtpSettings from './SmtpSettings.svelte';
	let name = $state('');
	let title = $state('');
	let tagline = $state('');
	let footerText = $state('');
	let loading = $state(true);
	let saving = $state(false);
	let error = $state('');
	let saved = $state(false);
	let exporting = $state<'zip' | 'pdf' | null>(null);
	let exportError = $state('');
	onMount(async () => {
		await auth.init();
		if (!auth.hasRole('admin')) {
			goto('/');
			return;
		}
		try {
			const settings = await api.getSettings();
			name = settings.cookbook_name;
			title = settings.home_title;
			tagline = settings.home_tagline;
			footerText = settings.footer_text;
		} catch {
			error = 'Einstellungen konnten nicht geladen werden.';
		} finally {
			loading = false;
		}
	});
	async function save(resetTagline = false) {
		if (!name.trim() || !title.trim()) {
			error = 'Name und Überschrift dürfen nicht leer sein.';
			return;
		}
		saving = true;
		error = '';
		saved = false;
		try {
			const settings = await api.updateSettings({
				cookbook_name: name.trim(),
				home_title: title.trim(),
				home_tagline: resetTagline ? '' : tagline,
				footer_text: footerText
			});
			cookbook.settings = settings;
			name = settings.cookbook_name;
			title = settings.home_title;
			tagline = settings.home_tagline;
			footerText = settings.footer_text;
			saved = true;
		} catch {
			error = 'Einstellungen konnten nicht gespeichert werden.';
		} finally {
			saving = false;
		}
	}

	async function exportCookbook(format: 'zip' | 'pdf') {
		if (exporting) return;
		exporting = format;
		exportError = '';
		try {
			const response = await fetch('/api/settings/export/' + format, {
				credentials: 'include',
				cache: 'no-store'
			});
			if (!response.ok) {
				let detail = '';
				try {
					const body = await response.json();
					if (typeof body.detail === 'string') detail = body.detail;
				} catch {
					// Use the HTTP status for non-JSON errors.
				}
				throw new Error(
					response.status === 403
						? 'Nur Administratoren dürfen das Kochbuch exportieren.'
						: response.status === 503
							? 'Der Export konnte nicht vollständig erstellt werden. Bitte Bilder und Daten prüfen.'
							: detail || 'Export fehlgeschlagen (HTTP ' + response.status + ').'
				);
			}
			downloadBlob(await response.blob(), 'heritagekitchen-cookbook.' + format, 10_000);
		} catch (cause) {
			exportError = cause instanceof Error ? cause.message : 'Export fehlgeschlagen.';
		} finally {
			exporting = null;
		}
	}
</script>

<svelte:head><title>Einstellungen · {cookbook.settings.cookbook_name}</title></svelte:head>
{#if !loading && auth.hasRole('admin')}
	<div class="settings-page">
		<h1>Kochbuch-Einstellungen</h1>
		{#if error}<p class="alert alert-error" role="alert">{error}</p>{/if}
		{#if saved}<p class="alert alert-success" role="status">Einstellungen gespeichert.</p>{/if}
		<form
			class="card"
			onsubmit={(event) => {
				event.preventDefault();
				save();
			}}
		>
			<h2>Darstellung</h2>
			<div class="field-pair">
				<div class="field">
					<label for="cookbook-name">Name des Kochbuchs</label>
					<input id="cookbook-name" bind:value={name} maxlength="100" required />
				</div>
				<div class="field">
					<label for="home-title">Überschrift der Startseite</label>
					<input id="home-title" bind:value={title} maxlength="100" required />
				</div>
			</div>
			<div class="field">
				<label for="home-tagline">Leitsatz auf der Startseite</label><textarea
					id="home-tagline"
					bind:value={tagline}
					maxlength="200"
					rows="3"
					aria-describedby="home-tagline-hint"
				></textarea>
				<span id="home-tagline-hint" class="muted">{tagline.length} / 200 Zeichen</span>
			</div>
			<div class="field">
				<label for="footer-text">Footertext</label><input
					id="footer-text"
					bind:value={footerText}
					maxlength="200"
					aria-describedby="footer-text-hint"
				/>
				<span id="footer-text-hint" class="muted">
					{footerText.length} / 200 Zeichen · Leer lassen zeigt den Kochbuchnamen an.
				</span>
			</div>
			<div class="settings-actions">
				<button class="btn btn-secondary" type="button" onclick={() => save(true)} disabled={saving}>
					Leitsatz zurücksetzen
				</button>
				<button class="btn btn-primary" disabled={saving}>
					{saving ? 'Speichert …' : 'Speichern'}
				</button>
			</div>
		</form>
		<SmtpSettings />
		<section class="card" aria-labelledby="export-heading">
			<h2 id="export-heading">Gesamtes Kochbuch exportieren</h2>
			<p>
				Der ZIP-Export enthält Rezepte, Kategorien, Bilder, Kommentare und Bewertungen.
				Das Gesamt-PDF ist zum Lesen und Drucken gedacht. Es enthält keine Kommentare oder Bewertungen.
			</p>
			<p class="muted">Der Export ist kein Backup und kann nicht wieder importiert werden. Anmeldekonten und Zugangsdaten werden nicht exportiert.</p>
			{#if exportError}<p class="alert alert-error" role="alert">{exportError}</p>{/if}
			<p role="status">
				{exporting === 'zip' ? 'Erstellt ZIP …' : exporting === 'pdf' ? 'Erstellt PDF …' : ''}
			</p>
			<div class="settings-actions">
				<button class="btn btn-secondary" type="button" aria-disabled={exporting !== null} onclick={() => exportCookbook('zip')}>
					JSON-ZIP herunterladen
				</button>
				<button class="btn btn-secondary" type="button" aria-disabled={exporting !== null} onclick={() => exportCookbook('pdf')}>
					Gesamt-PDF herunterladen
				</button>
			</div>
		</section>
	</div>
{/if}
