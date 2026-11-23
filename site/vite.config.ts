import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

// Static build: nginx serves the prerendered/SPA-fallback files, no Node
// server needed inside the container. The app talks to the backend via
// relative /api and /media paths (no fixed host), so in dev those are
// proxied straight to the FastAPI backend running on :8000.
const backendTarget = 'http://127.0.0.1:8000';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter({
				fallback: 'index.html'
			}),
		})
	],
	resolve: {
		alias: { $lib: fileURLToPath(new URL('./src/lib', import.meta.url)) }
	},
	server: {
		proxy: {
			'/api': { target: backendTarget, changeOrigin: true },
			'/media': { target: backendTarget, changeOrigin: true }
		}
	},
	preview: {
		proxy: {
			'/api': { target: backendTarget, changeOrigin: true },
			'/media': { target: backendTarget, changeOrigin: true }
		}
	}
});
