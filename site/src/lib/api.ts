import type {
	Settings,
	SmtpSettings,
	SmtpSettingsUpdate,
	Category,
	Favorite,
	FavoritePreferences,
	FavoriteSort,
	Recipe,
	RecipeComment,
	RecipeImage,
	RecipeInput,
	RecipeList,
	RecipeRatingSummary,
	User,
	UserDetail,
	UserRole,
	ViewPreferences,
	ViewPreferencesUpdate
} from './types';
import { get } from 'svelte/store';
import { OFFLINE_HEADER } from './offline/types.ts';
import { deviceSession, offlineStorageAvailable } from './offline/idb-storage.ts';
import { getOfflineWipeChannel, OFFLINE_WIPE_MESSAGE } from './offline/wipe-channel.ts';
import { installedApp } from './offline/installed.ts';
import { offlineConnection } from './offline/connection.ts';

export class ApiError extends Error {
	status: number;
	detail: unknown;
	constructor(status: number, message: string, detail?: unknown) {
		super(message);
		this.status = status;
		this.detail = detail;
	}
}

const errorTranslations = new Map([
	['Not authenticated.', 'Melde dich an, um fortzufahren.'],
	['Your role does not allow this action.', 'Du hast keine Berechtigung für diese Aktion.'],
	[
		'At least one administrator account must remain active.',
		'Mindestens ein Administratorkonto muss aktiv bleiben.'
	],
	[
		'Too many login attempts. Please try again later.',
		'Zu viele Anmeldeversuche. Versuch es später noch einmal.'
	],
	[
		'Username or email already registered.',
		'Benutzername oder E-Mail-Adresse ist bereits vergeben.'
	],
	['User not found.', 'Benutzerkonto nicht gefunden.'],
	[
		'Only pending registrations can be rejected.',
		'Diese Registrierung wartet nicht mehr auf Freischaltung.'
	],
	['Recipe not found.', 'Rezept nicht gefunden.'],
	['Comment not found.', 'Kommentar nicht gefunden.'],
	['You cannot edit this comment.', 'Du darfst diesen Kommentar nicht bearbeiten.'],
	['You cannot delete this comment.', 'Du darfst diesen Kommentar nicht löschen.'],
	['Category not found.', 'Kategorie nicht gefunden.'],
	['Ingredient group does not exist.', 'Die Zutatengruppe gibt es nicht.']
]);

let recipeVersionListener: ((before: number, after: number) => void) | null = null;

export function setRecipeVersionListener(listener: ((before: number, after: number) => void) | null) {
	recipeVersionListener = listener;
}

export function reportRecipeVersion(before: number, after: number) {
	recipeVersionListener?.(before, after);
}

async function request<T>(path: string, init?: RequestInit, fetcher = fetch): Promise<T> {
	// Offline the cookbook is read-only: changes are neither saved nor queued.
	if (init?.method && init.method !== 'GET' && path !== '/api/auth/logout' && get(offlineConnection))
		throw new ApiError(0, 'Ohne Serververbindung sind keine Änderungen möglich.');
	let response: Response;
	const canReadOffline = installedApp() && (!init?.method || init.method === 'GET');
	const headers = canReadOffline
		? { ...init?.headers, 'X-Offline-Read': '1' }
		: init?.body && !(init.body instanceof FormData)
			? { 'Content-Type': 'application/json', ...init.headers }
			: init?.headers;
	try {
		response = await fetcher(path, {
			credentials: 'include',
			...(canReadOffline ? { cache: 'no-store' } : {}),
			...init,
			headers
		});
	} catch (error) {
		if (!(error instanceof DOMException && error.name === 'AbortError')) offlineConnection.set(true);
		throw error;
	}
	if (!response.headers?.has('X-Local-Logout'))
		offlineConnection.set(response.headers?.get(OFFLINE_HEADER) === '1');

	const versionBefore = Number(response.headers?.get('X-Recipe-Version-Before'));
	const versionAfter = Number(response.headers?.get('X-Recipe-Version'));
	if (response.ok && versionBefore > 0 && versionAfter > 0) reportRecipeVersion(versionBefore, versionAfter);

	if (response.status === 204) {
		return undefined as T;
	}

	let data: unknown = null;
	const text = await response.text();
	if (text) {
		try {
			data = JSON.parse(text);
		} catch {
			data = text;
		}
	}

	if (!response.ok) {
		const detail =
			data && typeof data === 'object' && 'detail' in data ? data.detail : undefined;
		const message =
			typeof detail === 'string'
				? (errorTranslations.get(detail) ?? detail)
				: `Anfrage fehlgeschlagen (${response.status})`;
		throw new ApiError(response.status, message, detail);
	}

	return data as T;
}

function json(body: unknown) {
	return JSON.stringify(body);
}

// --- Auth ---------------------------------------------------------------

export function getSettings(fetcher = fetch): Promise<Settings> {
	return request('/api/settings', { cache: 'no-store' }, fetcher);
}

export function updateSettings(settings: Partial<Settings>): Promise<Settings> {
	return request('/api/settings', { method: 'PUT', body: json(settings) });
}

export function getSmtpSettings(): Promise<SmtpSettings> {
	return request('/api/settings/smtp', { cache: 'no-store' });
}

export function updateSmtpSettings(settings: SmtpSettingsUpdate): Promise<SmtpSettings> {
	return request('/api/settings/smtp', { method: 'PUT', body: json(settings) });
}

export function sendSmtpTest(recipient: string, settings?: SmtpSettingsUpdate): Promise<SmtpSettings> {
	return request('/api/settings/smtp/test', { method: 'POST', body: json({ recipient, settings }) });
}

export function getCurrentUser(): Promise<User> {
	return request<User>('/api/auth/me', { cache: 'no-store' });
}

export function updateProfile(update: {
	username?: string;
	email?: string | null;
	current_password?: string;
}): Promise<User> {
	return request<User>('/api/auth/me', { method: 'PATCH', body: json(update) });
}

export function setProfileImage(file: File): Promise<User> {
	const data = new FormData();
	data.set('image', file);
	return request<User>('/api/auth/me/image', { method: 'POST', body: data });
}

export function removeProfileImage(): Promise<User> {
	return request<User>('/api/auth/me/image', { method: 'DELETE' });
}

export function getViewPreferences(userId: number): Promise<ViewPreferences> {
	return request(`/api/users/${userId}/view-preferences`, { cache: 'no-store' });
}

export function updateViewPreferences(
	userId: number,
	update: ViewPreferencesUpdate
): Promise<void> {
	return request(`/api/users/${userId}/view-preferences`, {
		method: 'PATCH',
		body: json(update)
	});
}

export function login(identifier: string, password: string): Promise<User> {
	return request<User>('/api/auth/login', {
		method: 'POST',
		body: json({ username: identifier, password })
	});
}

export async function logout(): Promise<void> {
	const options = { method: 'POST', signal: AbortSignal.timeout(8000) };
	if (!offlineStorageAvailable() || navigator.serviceWorker?.controller)
		return request<void>('/api/auth/logout', options);

	// A newly opened tab might not yet be controlled by the service worker.
	await deviceSession.revoke({ logout: true });
	getOfflineWipeChannel()?.postMessage(OFFLINE_WIPE_MESSAGE);
	const epoch = await deviceSession.epoch();
	try {
		await request<void>('/api/auth/logout', options);
	} catch (error) {
		if (error instanceof ApiError && error.status !== 401) throw error;
		if (!(error instanceof ApiError)) return;
	}
	await deviceSession.finishLogout(epoch);
}

export function changePassword(current_password: string, new_password: string): Promise<void> {
	return request<void>('/api/auth/password', {
		method: 'POST',
		body: json({ current_password, new_password })
	});
}

type AccountMailAvailability = { available: boolean; hint?: string };

export function resetAvailable(): Promise<AccountMailAvailability> {
	return request('/api/auth/reset-available', { cache: 'no-store' });
}

export function emailAvailable(): Promise<AccountMailAvailability> {
	return request('/api/auth/email-available', { cache: 'no-store' });
}

export function verifyEmail(token: string): Promise<void> {
	return request('/api/auth/verify-email', { method: 'POST', body: json({ token }) });
}

export function requestPasswordReset(email: string): Promise<void> {
	return request('/api/auth/reset-request', { method: 'POST', body: json({ email }) });
}

export function sendUserPasswordReset(userId: number): Promise<void> {
	return request(`/api/users/${userId}/password-reset`, { method: 'POST' });
}

export function resetPassword(token: string, new_password: string): Promise<void> {
	return request('/api/auth/reset-password', {
		method: 'POST',
		body: json({ token, new_password })
	});
}

export function registrationStatus(): Promise<{ first_account: boolean }> {
	return request('/api/auth/registration-status', { cache: 'no-store' });
}

export function register(input: {
	username: string;
	email?: string | null;
	password: string;
}): Promise<User> {
	return request<User>('/api/auth/register', {
		method: 'POST',
		body: json(input)
	});
}

// --- Categories -----------------------------------------------------------

export function listCategories(): Promise<Category[]> {
	return request<Category[]>('/api/categories');
}

export function getCategory(id: number): Promise<Category> {
	return request<Category>(`/api/categories/${id}`);
}

export function createCategory(input: {
	name: string;
	description?: string | null;
	image_alt_text?: string | null;
}): Promise<Category> {
	return request<Category>('/api/categories', { method: 'POST', body: json(input) });
}

export function updateCategory(
	id: number,
	input: Partial<{
		name: string;
		description: string | null;
		image_alt_text: string | null;
	}>
): Promise<Category> {
	return request<Category>(`/api/categories/${id}`, { method: 'PUT', body: json(input) });
}

export function setCategoryImage(id: number, file: File): Promise<Category> {
	const formData = new FormData();
	formData.append('image', file);
	return request<Category>(`/api/categories/${id}/image`, { method: 'POST', body: formData });
}

export function removeCategoryImage(id: number): Promise<Category> {
	return request<Category>(`/api/categories/${id}/image`, { method: 'DELETE' });
}

export function deleteCategory(id: number): Promise<void> {
	return request<void>(`/api/categories/${id}`, { method: 'DELETE' });
}

// --- Recipes --------------------------------------------------------------

export function listRecipes(params: {
	sort?: 'title' | 'newest' | 'manual';
	search?: string;
	category_id?: number;
	page?: number;
	page_size?: number;
}): Promise<RecipeList> {
	const query = new URLSearchParams({ summary: 'true' });
	if (params.sort) query.set('sort', params.sort);
	if (params.search) query.set('search', params.search);
	if (params.category_id) query.set('category_id', String(params.category_id));
	query.set('page', String(params.page ?? 1));
	query.set('page_size', String(params.page_size ?? 20));
	return request<RecipeList>(`/api/recipes?${query.toString()}`);
}

export function saveRecipeOrder(categoryId: number, recipeIds: number[]): Promise<void> {
	return request<void>('/api/recipes/order', {
		method: 'PUT',
		body: json({ category_id: categoryId, recipe_ids: recipeIds })
	});
}

export function getRecipe(id: number): Promise<Recipe> {
	return request<Recipe>(`/api/recipes/${id}`, { cache: 'no-store' });
}

export function createRecipe(input: RecipeInput): Promise<Recipe> {
	return request<Recipe>('/api/recipes', { method: 'POST', body: json(input) });
}

export function getRecipeRatings(id: number): Promise<RecipeRatingSummary> {
	return request<RecipeRatingSummary>(`/api/recipes/${id}/ratings`);
}

export function saveRecipeRating(id: number, stars: number): Promise<RecipeRatingSummary> {
	return request<RecipeRatingSummary>(`/api/recipes/${id}/ratings`, {
		method: 'PUT',
		body: json({ stars })
	});
}

export function removeRecipeRating(id: number): Promise<RecipeRatingSummary> {
	return request<RecipeRatingSummary>(`/api/recipes/${id}/ratings`, { method: 'DELETE' });
}

export function updateRecipe(
	id: number,
	input: Partial<RecipeInput>,
	expectedVersion: number
): Promise<Recipe> {
	return request<Recipe>(`/api/recipes/${id}`, {
		method: 'PUT',
		body: json(input),
		headers: { 'If-Match': `"${expectedVersion}"` }
	});
}

export function deleteRecipe(id: number): Promise<void> {
	return request<void>(`/api/recipes/${id}`, { method: 'DELETE' });
}

export function listRecipeComments(recipeId: number): Promise<RecipeComment[]> {
	return request(`/api/recipes/${recipeId}/comments`, { cache: 'no-store' });
}

export function createRecipeComment(recipeId: number, text: string): Promise<RecipeComment> {
	return request(`/api/recipes/${recipeId}/comments`, { method: 'POST', body: json({ text }) });
}

export function updateRecipeComment(
	recipeId: number,
	commentId: number,
	text: string
): Promise<RecipeComment> {
	return request(`/api/recipes/${recipeId}/comments/${commentId}`, {
		method: 'PUT',
		body: json({ text })
	});
}

export function deleteRecipeComment(recipeId: number, commentId: number): Promise<void> {
	return request(`/api/recipes/${recipeId}/comments/${commentId}`, { method: 'DELETE' });
}

export function uploadRecipeImage(
	recipeId: number,
	file: File,
	expectedVersion: number,
	altText?: string
): Promise<RecipeImage> {
	const formData = new FormData();
	formData.append('image', file);
	if (altText) formData.append('alt_text', altText);
	return request<RecipeImage>(`/api/recipes/${recipeId}/images`, {
		method: 'POST',
		headers: { 'If-Match': `"${expectedVersion}"` },
		body: formData
	});
}

export function setMainImage(imageId: number, expectedVersion: number): Promise<RecipeImage> {
	return request<RecipeImage>(`/api/recipe-images/${imageId}`, {
		method: 'PUT',
		headers: { 'If-Match': `"${expectedVersion}"` },
		body: json({ is_main: true })
	});
}

export function reorderRecipeImages(
	recipeId: number,
	imageIds: number[],
	expectedVersion: number
): Promise<RecipeImage[]> {
	return request<RecipeImage[]>(`/api/recipes/${recipeId}/images/order`, {
		method: 'PUT',
		headers: { 'If-Match': `"${expectedVersion}"` },
		body: json({ image_ids: imageIds })
	});
}

export function updateRecipeImageAltText(
	imageId: number,
	altText: string | null,
	expectedVersion: number
): Promise<RecipeImage> {
	return request<RecipeImage>(`/api/recipe-images/${imageId}`, {
		method: 'PUT',
		headers: { 'If-Match': `"${expectedVersion}"` },
		body: json({ alt_text: altText })
	});
}

export function cropRecipeImage(
	imageId: number,
	file: File,
	expectedVersion: number
): Promise<RecipeImage> {
	const data = new FormData();
	data.append('image', file);
	return request<RecipeImage>(`/api/recipe-images/${imageId}/crop`, {
		method: 'PUT',
		headers: { 'If-Match': `"${expectedVersion}"` },
		body: data
	});
}

export function deleteRecipeImage(imageId: number, expectedVersion: number): Promise<void> {
	return request<void>(`/api/recipe-images/${imageId}`, {
		method: 'DELETE',
		headers: { 'If-Match': `"${expectedVersion}"` }
	});
}

// --- Favorites --------------------------------------------------------------

export function listFavorites(sort?: FavoriteSort, expectedUserId?: number): Promise<Favorite[]> {
	const query = new URLSearchParams();
	if (sort) query.set('sort', sort);
	if (expectedUserId !== undefined) query.set('expected_user_id', String(expectedUserId));
	const params = query.toString();
	const path = params ? '/api/favorites?' + params : '/api/favorites';
	return request(path, { cache: 'no-store' });
}

export function getFavoritePreferences(userId: number): Promise<FavoritePreferences> {
	return request('/api/favorites/preferences?expected_user_id=' + userId, { cache: 'no-store' });
}

export function updateFavoritePreferences(
	userId: number,
	update: Partial<FavoritePreferences>
): Promise<void> {
	return request('/api/favorites/preferences?expected_user_id=' + userId, {
		method: 'PATCH',
		body: json(update)
	});
}

export function setFavoriteOrder(userId: number, favoriteIds: number[]): Promise<Favorite[]> {
	return request('/api/favorites/order?expected_user_id=' + userId, {
		method: 'PUT',
		body: json({ favorite_ids: favoriteIds })
	});
}

export function addFavorite(recipeId: number, userId: number): Promise<Favorite> {
	return request('/api/favorites?expected_user_id=' + userId, {
		method: 'POST',
		body: json({ recipe_id: recipeId })
	});
}

export function removeFavorite(favoriteId: number, userId: number): Promise<void> {
	return request(`/api/favorites/${favoriteId}?expected_user_id=${userId}`, { method: 'DELETE' });
}

// --- Users (admin) ----------------------------------------------------------

export function createUser(input: {
	username: string;
	email?: string | null;
	password: string;
	role?: UserRole;
	is_active?: boolean;
}): Promise<User> {
	return request<User>('/api/users', { method: 'POST', body: json(input) });
}

export function listUsers(): Promise<User[]> {
	return request<User[]>('/api/users');
}

export function getUser(id: number): Promise<UserDetail> {
	return request<UserDetail>(`/api/users/${id}`);
}

export function updateUser(
	id: number,
	input: Partial<{
		username: string;
		email: string | null;
		password: string;
		current_password: string;
		role: string;
		is_active: boolean;
	}>
): Promise<User> {
	return request<User>(`/api/users/${id}`, { method: 'PUT', body: json(input) });
}

export function deleteUser(id: number): Promise<void> {
	return request<void>(`/api/users/${id}`, { method: 'DELETE' });
}

export function rejectRegistration(id: number): Promise<void> {
	return request<void>(`/api/users/${id}/registration`, { method: 'DELETE' });
}
