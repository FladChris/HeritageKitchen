// Visibility and asynchronous acquisition are managed together so a late request
// cannot keep the screen awake after leaving cooking mode.
export interface ScreenLock {
	release(): Promise<void>;
}
export function keepScreenAwake(
	request: (() => Promise<ScreenLock>) | undefined,
	visibility: Pick<Document, 'visibilityState' | 'addEventListener' | 'removeEventListener'>,
	onUnavailable: () => void
): () => void {
	let disposed = false;
	let lock: ScreenLock | null = null;
	let pending = false;
	async function acquire() {
		if (disposed || visibility.visibilityState !== 'visible' || lock || pending) return;
		if (!request) {
			onUnavailable();
			return;
		}
		pending = true;
		try {
			const next = await request();
			if (disposed || visibility.visibilityState !== 'visible') await next.release();
			else lock = next;
		} catch {
			if (!disposed) onUnavailable();
		} finally {
			pending = false;
		}
	}
	function release() {
		const previous = lock;
		lock = null;
		void previous?.release().catch(() => {});
	}
	function changed() {
		if (visibility.visibilityState === 'visible') void acquire();
		else release();
	}
	visibility.addEventListener('visibilitychange', changed);
	void acquire();
	return () => {
		disposed = true;
		visibility.removeEventListener('visibilitychange', changed);
		release();
	};
}
