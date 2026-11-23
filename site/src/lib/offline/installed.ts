export function installedApp(): boolean {
	return (
		typeof window !== 'undefined' &&
		(window.matchMedia?.('(display-mode: standalone)')?.matches === true ||
			(navigator as Navigator & { standalone?: boolean }).standalone === true)
	);
}

export function offlineImage(path: string): string {
	if (!path.startsWith('/media/') || !installedApp()) return path;
	const url = new URL(path, window.location.origin);
	url.searchParams.set('heritagekitchen-offline', '1');
	return url.pathname + url.search;
}
