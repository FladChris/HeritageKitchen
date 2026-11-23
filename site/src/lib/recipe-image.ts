import type { RecipeImage } from './types';

export function coverImage(images: RecipeImage[]): RecipeImage | undefined {
	return images.find((image) => image.is_main) ?? images[0];
}
