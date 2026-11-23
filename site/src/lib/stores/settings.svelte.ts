import type { Settings } from '$lib/types';
export const defaultSettings: Settings = {
	cookbook_name: 'Heritage Kitchen',
	home_title: 'Lieblingsrezepte',
	home_tagline: 'Unsere Rezepte, gesammelt und weitergegeben.',
	footer_text: ''
};
export const cookbook = $state({ settings: defaultSettings });
