import { render, screen, waitFor } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import RecipeCard from '$lib/components/RecipeCard.svelte';
import type { RecipeSummary } from '$lib/types';

const recipe: RecipeSummary = {
	id: 1,
	version: 1,
	title: 'Apfelkuchen',
	summary: null,
	origin_person: null,
	preparation_days: 1,
	preparation_time: null,
	cooking_time: null,
	cooking_time_max: null,
	rest_time: null,
	rest_time_max: null,
	servings: null,
	created_at: '',
	updated_at: '',
	images: [],
	category: null,
	category_id: null
};

test.each(['list', 'grid'] as const)('%s shows a placeholder before upload and after deletion', async (layout) => {
	const { rerender } = render(RecipeCard, { recipe, layout });
	const card = screen.getByRole('link', { name: 'Apfelkuchen' });
	const placeholder = () => card.querySelector('.photo-placeholder[aria-hidden="true"] svg');
	expect(placeholder()).toBeTruthy();
	expect(card.querySelector('img')).toBeNull();

	await rerender({ recipe: { ...recipe, images: [{
		id: 1, recipe_id: 1, file_path: '/media/cake.jpg', alt_text: 'Kuchen', is_main: true
	}] } });
	await waitFor(() => expect(card.querySelector('img')?.getAttribute('src')).toBe('/media/cake.jpg'));
	expect(placeholder()).toBeNull();

	await rerender({ recipe });
	await waitFor(() => expect(placeholder()).toBeTruthy());
	expect(card.querySelector('img')).toBeNull();
});
