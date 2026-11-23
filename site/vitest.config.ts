import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { fileURLToPath } from 'node:url';
const local = (path: string) => fileURLToPath(new URL(path, import.meta.url));
export default defineConfig({
	tsconfig: local('./tests/tsconfig.json'),
	plugins: [svelte({ configFile: false, compilerOptions: { runes: true } })],
	resolve: {
		conditions: ['browser'],
		alias: {
			$lib: local('./src/lib'),
			'$app/state': local('./tests/ui/navigation.svelte.ts'),
			'$app/navigation': local('./tests/ui/navigation.svelte.ts')
		}
	},
	test: {
		environment: 'jsdom',
		include: ['tests/ui/**/*.test.ts'],
		setupFiles: ['tests/ui/setup.ts'],
		restoreMocks: true
	}
});
