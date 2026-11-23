<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';

	let {
		id,
		value = $bindable(),
		autocomplete,
		required = false,
		minlength,
		maxlength,
		placeholder,
		disabled = false,
		'aria-describedby': describedBy,
		'aria-label': label
	}: {
		id: string;
		value: string;
		autocomplete?: HTMLInputAttributes['autocomplete'];
		required?: boolean;
		minlength?: number;
		maxlength?: number;
		placeholder?: string;
		disabled?: boolean;
		'aria-describedby'?: string;
		'aria-label'?: string;
	} = $props();

	let visible = $state(false);
</script>

<div class="password-input">
	<input
		{id}
		type={visible ? 'text' : 'password'}
		bind:value
		{autocomplete}
		{required}
		{minlength}
		{maxlength}
		{placeholder}
		{disabled}
		aria-describedby={describedBy}
		aria-label={label}
	/>
	<button
		type="button"
		aria-label={visible ? 'Passwort verbergen' : 'Passwort anzeigen'}
		title={visible ? 'Passwort verbergen' : 'Passwort anzeigen'}
		aria-pressed={visible}
		{disabled}
		onclick={() => (visible = !visible)}
	>
		<svg
			class="icon"
			viewBox="0 0 24 24"
			width="20"
			height="20"
			fill="none"
			stroke="currentColor"
			stroke-width="1.75"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
		>
			{#if visible}
				<path d="M12 2v2 M3 13a9 9 0 0 1 18 0 Z" />
			{:else}
				<path d="M12 10V8 M3 19a9 9 0 0 1 18 0 Z" />
			{/if}
			<path d="M2 21h20 M5 19h14" />
		</svg>
	</button>
</div>

<style>
	.password-input {
		display: flex;
		align-items: stretch;
		gap: 0.35rem;
	}

	.password-input input {
		flex: 1;
		min-width: 0;
	}

	.password-input button {
		display: grid;
		place-items: center;
		flex: 0 0 44px;
		min-height: 44px;
		padding: 0;
		border: 1px solid var(--color-border-strong);
		border-radius: var(--radius-sm);
		background: var(--color-surface-raised);
		color: var(--color-text);
	}

	.password-input button:hover {
		background: var(--color-surface);
	}
</style>
