// Types mirror the backend's Pydantic schemas 1:1 (see
// app/api/schemas/*.py in the repo root). Keep them in sync when the
// backend schemas change.

export type UserRole = 'reader' | 'editor' | 'admin';

export interface User {
	id: number;
	username: string;
	email: string | null;
	email_verified_at: string | null;
	profile_image_path?: string | null;
	role: UserRole;
	is_active: boolean;
	pending_approval: boolean;
	created_at: string;
}

export interface Favorite {
	id: number;
	user_id: number;
	recipe_id: number;
	created_at: string | null;
}

export type FavoriteSort = 'recent' | 'name' | 'manual';

export interface FavoritePreferences {
	sort: FavoriteSort;
	recipe_view: 'list' | 'grid';
}

export interface RecipeComment {
	id: number;
	recipe_id: number;
	author_id: number | null;
	author_username: string | null;
	text: string;
	created_at: string;
	edited_at: string | null;
}

export interface UserDetail extends User {
	updated_at: string;
	favorites: Favorite[];
}

export interface Category {
	id: number;
	recipe_count: number | null;
	name: string;
	description: string | null;
	image_path: string | null;
	image_alt_text: string | null;
}

export interface RecipeImage {
	id: number;
	recipe_id: number;
	file_path: string;
	alt_text: string | null;
	is_main: boolean;
}

export interface RecipeRatingSummary {
	average: number | null;
	count: number;
	ratings: { username: string; stars: number }[];
}

export interface RecipeIngredient {
	id: number;
	recipe_id: number;
	position: number;
	group_position: number | null;
	name: string;
	amount: string | null;
	unit: string | null;
	note: string | null;
}

export interface IngredientGroup {
	id: number;
	recipe_id: number;
	position: number;
	name: string;
}

export interface IngredientGroupInput {
	position: number;
	name: string;
}

export type StepTimeKind = 'preparation' | 'cooking' | 'rest';

export interface RecipeStep {
	id: number;
	recipe_id: number;
	position: number;
	instruction: string;
	heading: string | null;
	is_important: boolean;
	note: string | null;
	duration_minutes: number | null;
	time_kind: StepTimeKind | null;
	day: number;
}

export interface RecipeSummary {
	id: number;
	version: number;
	title: string;
	summary: string | null;
	preparation_days: number;
	preparation_time: number | null;
	cooking_time: number | null;
	cooking_time_max: number | null;
	rest_time: number | null;
	rest_time_max: number | null;
	step_times?: Partial<Record<StepTimeKind, number | null>>;
	servings: number | null;
	origin_person: string | null;
	category_id: number | null;
	created_at: string;
	updated_at: string;
	category: Category | null;
	images: RecipeImage[];
}

export interface Recipe extends RecipeSummary {
	day_titles: string[] | null;
	history: string | null;
	notes: string | null;
	important_notes: string | null;
	ingredients: RecipeIngredient[];
	ingredient_groups: IngredientGroup[];
	steps: RecipeStep[];
}

export interface OtherCategoryHit {
	id: number;
	name: string;
	count: number;
}

export interface RecipeList {
	items: RecipeSummary[];
	total: number;
	other_categories?: OtherCategoryHit[];
	page: number;
	page_size: number;
}

export interface IngredientInput {
	position: number;
	group_position: number | null;
	name: string;
	amount: string | null;
	unit: string | null;
	note: string | null;
}

export interface StepInput {
	position: number;
	instruction: string;
	heading: string | null;
	is_important: boolean;
	note: string | null;
	duration_minutes: number | null;
	time_kind: StepTimeKind | null;
	day: number;
}

export interface RecipeInput {
	history: string | null;
	day_titles: string[] | null;
	title: string;
	summary: string | null;
	preparation_days: number;
	preparation_time: number | null;
	cooking_time: number | null;
	cooking_time_max: number | null;
	rest_time: number | null;
	rest_time_max: number | null;
	servings: number | null;
	origin_person: string | null;
	notes: string | null;
	important_notes: string | null;
	category_id: number | null;
	ingredients: IngredientInput[];
	ingredient_groups: IngredientGroupInput[];
	steps: StepInput[];
}

export interface RecipeConflictDetail {
	code: 'recipe_version_conflict';
	expected_version: number;
	current_version: number;
	current: Record<string, unknown>;
}

export interface RecipeConflict extends RecipeConflictDetail {
	changes: Record<string, { before: unknown; after: unknown }>;
}

export interface Settings {
	home_tagline: string;
	cookbook_name: string;
	home_title: string;
	footer_text: string;
}

export interface SmtpSettings {
	version: number;
	host: string;
	port: number;
	encryption: 'none' | 'starttls' | 'tls';
	username: string;
	sender: string;
	has_password: boolean;
	status: 'not_configured' | 'untested' | 'tested';
	account_mail_hint: string | null;
}

export type SmtpSettingsUpdate = Omit<SmtpSettings, 'has_password' | 'status' | 'account_mail_hint'> & {
	password: string;
};

export interface ViewPreferences {
	category_sort: 'manual' | 'name' | 'count';
	recipe_view: 'list' | 'grid';
	category_ids: number[];
}

export type ViewPreferencesUpdate = Partial<Omit<ViewPreferences, 'category_ids'>> & {
	category_order?: { category_ids: number[] };
};
