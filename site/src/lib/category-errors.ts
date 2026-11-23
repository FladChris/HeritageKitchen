import { ApiError } from '$lib/api';

export function categoryNameError(error: unknown, fallback: string): string {
	return error instanceof ApiError && error.status === 409
		? 'Dieser Kategoriename ist bereits vergeben.'
		: fallback;
}
