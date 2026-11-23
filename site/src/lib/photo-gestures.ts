export function swipeDirection(dx: number, dy: number, scale: number): -1 | 0 | 1 {
	return scale <= 1 && Math.abs(dx) >= 50 && Math.abs(dx) > Math.abs(dy) * 1.5
		? dx < 0
			? 1
			: -1
		: 0;
}
export function zoomScale(initial: number, distance: number, initialDistance: number): number {
	return Math.min(5, Math.max(1, (initial * distance) / Math.max(1, initialDistance)));
}
export function wrappedIndex(index: number, delta: number, length: number): number {
	return length ? (((index + delta) % length) + length) % length : 0;
}
