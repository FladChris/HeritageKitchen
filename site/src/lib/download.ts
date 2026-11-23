/** Start a browser download and release its object URL after the browser has read it. */
export function downloadBlob(blob: Blob, filename: string, revokeAfterMs = 60_000): void {
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = filename;
	try {
		document.body.appendChild(link);
		link.click();
	} finally {
		link.remove();
		window.setTimeout(() => URL.revokeObjectURL(url), revokeAfterMs);
	}
}
