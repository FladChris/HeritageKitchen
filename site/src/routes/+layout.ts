import { getSettings } from '$lib/api';
import type { LayoutLoad } from './$types';

// Static SPA build (adapter-static with a fallback document): the whole
// app is client-rendered so login-gated, per-user pages work without a
// Node server. See vite.config.ts for the adapter/proxy setup.
export const ssr = false;
export const prerender = false;

export const load: LayoutLoad = async ({ fetch }) => {
	try {
		return { settings: await getSettings(fetch) };
	} catch {
		return { settings: null };
	}
};
