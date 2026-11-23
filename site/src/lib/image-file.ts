/** Load an existing image as a file for the cropper, preserving its MIME type. */
export async function loadImageFile(path: string, filename: string): Promise<File> {
	const response = await fetch(path);
	if (!response.ok) throw new Error('Image unavailable');
	const blob = await response.blob();
	return new File([blob], filename, { type: blob.type });
}
