import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiError, listRecipes, login, saveRecipeOrder, updateRecipe, updateSettings } from '../src/lib/api.ts';
import { changedRecipeFields } from '../src/lib/recipe-conflicts.ts';

test('visible API errors use German text and retain their status', async (t) => {
	const responses = [
		new Response(JSON.stringify({ detail: 'Too many login attempts. Please try again later.' }), {
			status: 429
		}),
		new Response(JSON.stringify({ detail: [{ msg: 'Field required' }] }), { status: 422 })
	];
	t.mock.method(globalThis, 'fetch', async () => responses.shift());
	await assert.rejects(
		login('koch', 'passwort'),
		(error) =>
			error instanceof ApiError &&
			error.status === 429 &&
			error.message === 'Zu viele Anmeldeversuche. Versuch es später noch einmal.'
	);
	await assert.rejects(login('koch', ''), { message: 'Anfrage fehlgeschlagen (422)' });
});
test('list requests use lightweight summaries with explicit pagination and newest sorting', async (t) => {
	const urls = [];
	t.mock.method(globalThis, 'fetch', async (path) => {
		urls.push(new URL(path, 'http://localhost'));
		return new Response(JSON.stringify({ items: [], total: 0, page: 6, page_size: 20 }));
	});
	await listRecipes({ search: 'Brot & Butter', category_id: 2, page: 6, page_size: 20 });
	await listRecipes({ sort: 'newest', page_size: 3 });
	assert.equal(urls[0].searchParams.get('summary'), 'true');
	assert.equal(urls[0].searchParams.get('page'), '6');
	assert.equal(urls[0].searchParams.get('search'), 'Brot & Butter');
	assert.equal(urls[0].searchParams.get('category_id'), '2');
	assert.equal(urls[1].searchParams.get('sort'), 'newest');
	assert.equal(urls[1].searchParams.get('page_size'), '3');
});
test('personal recipe order is requested and saved per category', async (t) => {
	const calls = [];
	t.mock.method(globalThis, 'fetch', async (path, init) => {
		calls.push({ url: new URL(path, 'http://localhost'), init });
		return path.includes('/order')
			? new Response(null, { status: 204 })
			: new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }));
	});
	await listRecipes({ sort: 'manual', category_id: 2 });
	await saveRecipeOrder(2, [5, 3]);
	assert.equal(calls[0].url.searchParams.get('sort'), 'manual');
	assert.equal(calls[1].url.pathname, '/api/recipes/order');
	assert.equal(calls[1].init.method, 'PUT');
	assert.deepEqual(JSON.parse(calls[1].init.body), { category_id: 2, recipe_ids: [5, 3] });
});
test('recipe and settings updates send independent recipe content and cookbook names', async (t) => {
	const bodies = [];
	const headers = [];
	t.mock.method(globalThis, 'fetch', async (_path, init) => {
		bodies.push(JSON.parse(init.body));
		headers.push(init.headers);
		return new Response('{}');
	});
	await updateRecipe(1, {
		history: 'Oma\nSonntags',
		preparation_days: 2,
		steps: [{ position: 0, instruction: 'Für die 20-cm-Form 350 g Mehl verwenden.' }]
	}, 7);
	await updateSettings({ cookbook_name: 'Unsere Küche', home_title: 'Unser Kochbuch' });
	assert.deepEqual(bodies[0], {
		history: 'Oma\nSonntags',
		preparation_days: 2,
		steps: [{ position: 0, instruction: 'Für die 20-cm-Form 350 g Mehl verwenden.' }]
	});
	assert.equal(bodies[1].cookbook_name, 'Unsere Küche');
	assert.equal(headers[0]['If-Match'], '"7"');
	assert.equal(headers[0]['Content-Type'], 'application/json');
});

test('concurrent field comparison uses only the recipe opened in this browser', () => {
	const opened = {
		title: 'Apfelkuchen', category_id: 1, category: { name: 'Kuchen' },
		summary: null, preparation_time: 15, cooking_time: 35, cooking_time_max: null,
		rest_time: null, rest_time_max: null, servings: 4, history: null,
		preparation_days: 1, day_titles: null, origin_person: 'Oma',
		notes: null, important_notes: null,
		ingredient_groups: [],
		ingredients: [
			{ id: 1, position: 0, name: 'Mehl', amount: '500', unit: 'g', note: null, group_position: null }
		],
		steps: [], images: []
	};
	const current = {
		title: 'Besserer Apfelkuchen', category_id: 1, category_name: 'Kuchen',
		summary: null, preparation_time: 15, cooking_time: 35, cooking_time_max: null,
		rest_time: null, rest_time_max: null, servings: 4, history: null,
		preparation_days: 1, day_titles: null, origin_person: 'Oma',
		notes: null, important_notes: null,
		ingredient_groups: [],
		ingredients: [
			{ position: 0, name: 'Mehl', amount: '650.000', unit: 'g', note: null, group_position: null }
		],
		steps: [], images: []
	};
	const changes = changedRecipeFields(opened, current);
	assert.deepEqual(Object.keys(changes).sort(), ['ingredients', 'title']);
	assert.deepEqual(changes.title, { before: 'Apfelkuchen', after: 'Besserer Apfelkuchen' });
	assert.equal(changes.ingredients.after[0].amount, '650.000');
});

test('every image mutation sends the held version and advances it from response headers', async (t) => {
	const api = await import('../src/lib/api.ts');
	let heldVersion = 7;
	const calls = [];
	api.setRecipeVersionListener((before, after) => {
		assert.equal(before, heldVersion);
		heldVersion = after;
	});
	t.after(() => api.setRecipeVersionListener(null));
	t.mock.method(globalThis, 'fetch', async (path, init) => {
		calls.push({ path, init });
		assert.equal(init.headers['If-Match'], `"${heldVersion}"`);
		return new Response(init.method === 'DELETE' ? null : '{}', {
			status: init.method === 'DELETE' ? 204 : 200,
			headers: {
				'X-Recipe-Version-Before': String(heldVersion),
				'X-Recipe-Version': String(heldVersion + 1)
			}
		});
	});
	const file = new File(['photo'], 'photo.jpg', { type: 'image/jpeg' });
	await api.uploadRecipeImage(1, file, heldVersion, 'Cake');
	await api.setMainImage(2, heldVersion);
	await api.updateRecipeImageAltText(2, 'New alt', heldVersion);
	await api.cropRecipeImage(2, file, heldVersion);
	await api.reorderRecipeImages(1, [2, 1], heldVersion);
	await api.deleteRecipeImage(2, heldVersion);
	assert.equal(heldVersion, 13);
	assert.equal(calls.length, 6);
	assert.equal(calls[0].init.body.get('alt_text'), 'Cake');
	assert.equal(calls[0].init.headers['Content-Type'], undefined);
	assert.equal(calls[3].init.headers['Content-Type'], undefined);
});
