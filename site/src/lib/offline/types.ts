import type {
	Category,
	Favorite,
	FavoritePreferences,
	FavoriteSort,
	Recipe,
	RecipeComment,
	RecipeRatingSummary,
	RecipeSummary,
	Settings,
	User,
	ViewPreferences
} from '$lib/types';

// A complete cookbook snapshot for one account, published in a single transaction.
export interface OfflineSnapshot {
	generation: string;
	syncedAt: string;
	user: User;
	settings: Settings;
	categories: Category[];
	summaries: RecipeSummary[];
	recipes: Recipe[];
	comments: Record<number, RecipeComment[]>;
	// Snapshots saved before ratings sync have no ratings.
	ratings?: Record<number, RecipeRatingSummary>;
	favorites: Record<FavoriteSort, Favorite[]>;
	favoritePreferences: FavoritePreferences;
	viewPreferences: ViewPreferences;
	manualOrder: Record<number, number[]>;
}

export interface OfflineMeta {
	generation: string;
	previousGeneration?: string;
	userId: number;
	syncedAt: string;
}

export interface OfflineStatus {
	userId: number;
	state: 'pending' | 'complete' | 'failed';
	at: string;
	error?: string;
}

export interface OfflineStorage {
	readMeta(userId: number): Promise<OfflineMeta | null>;
	readSnapshot(userId: number): Promise<OfflineSnapshot | null>;
	// Atomically publishes the snapshot and successful status.
	commit(snapshot: OfflineSnapshot, lease?: string): Promise<void>;
	readStatus(userId: number): Promise<OfflineStatus | null>;
	writeStatus(status: OfflineStatus): Promise<void>;
	copyMedia(from: string, to: string, path: string): Promise<boolean>;
	putMedia(generation: string, path: string, response: Response): Promise<void>;
	getMedia(generation: string, path: string): Promise<Response | null>;
	discardMedia(generation: string): Promise<void>;
	pruneMedia(userId: number, keepPrevious?: boolean, lease?: string): Promise<void>;
}

export const OFFLINE_HEADER = 'X-Offline';
export const SYNC_HEADER = 'X-Offline-Sync';

// Project already-saved snapshots onto the current account schema as well.
export function offlineUser(user: User): User {
	return {
		id: user.id,
		username: user.username,
		email: user.email,
		email_verified_at: user.email_verified_at ?? null,
		profile_image_path: user.profile_image_path,
		role: user.role,
		is_active: user.is_active,
		pending_approval: user.pending_approval,
		created_at: user.created_at
	};
}
