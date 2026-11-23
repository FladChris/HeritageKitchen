import { onDestroy } from 'svelte';

export const page = $state({
	params: { id: '1' },
	url: new URL('http://localhost/'),
	state: {} as App.PageState
});
export function pushState(_url: string, state: App.PageState) {
	page.state = state;
}
type NavigationGuard = (navigation: { cancel: () => void; willUnload: boolean }) => void;
const guards = new Set<NavigationGuard>();
export function beforeNavigate(guard: NavigationGuard) {
	guards.add(guard);
	onDestroy(() => guards.delete(guard));
}
export function navigateAllowed(willUnload = false): boolean {
	let cancelled = false;
	for (const guard of guards) guard({ cancel: () => (cancelled = true), willUnload });
	return !cancelled;
}
export function goto(url: string) {
	if (!navigateAllowed()) return;
	page.url = new URL(url, 'http://localhost');
	page.state = {};
	const match = url.match(/^\/recipes\/(\d+)/);
	if (match) page.params.id = match[1];
}
