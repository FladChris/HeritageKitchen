<script lang="ts">
	import { cookbook } from '$lib/stores/settings.svelte';
</script>

<footer class="site-footer">
	<div class="container">
		<p class="muted">{cookbook.settings.footer_text || cookbook.settings.cookbook_name}</p>
	</div>
</footer>

<style>
	.site-footer {
		border-top: 1px solid var(--color-border);
		padding-block: 1.5rem;
		margin-top: 2rem;
	}
</style>
