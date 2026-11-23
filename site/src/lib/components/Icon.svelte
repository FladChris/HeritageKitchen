<script lang="ts">
	import {
		ArrowLeft,
		ArrowUp,
		ArrowDown,
		ChevronDown,
		GripVertical,
		ArrowUpDown,
		ChevronLeft,
		ChevronRight,
		Camera,
		Crop,
		Pencil,
		Trash2,
		Grid2X2,
		List,
		X,
		Star,
		Menu,
		Plus,
		UserRound,
		KeyRound,
		Settings,
		Users,
		LogOut
	} from '@lucide/svelte';
	const icons = {
		back: ArrowLeft,
		up: ArrowUp,
		down: ArrowDown,
		previous: ChevronLeft,
		expand: ChevronDown,
		grip: GripVertical,
		reorder: ArrowUpDown,
		next: ChevronRight,
		camera: Camera,
		crop: Crop,
		edit: Pencil,
		trash: Trash2,
		grid: Grid2X2,
		list: List,
		close: X,
		star: Star,
		menu: Menu,
		plus: Plus,
		user: UserRound,
		password: KeyRound,
		settings: Settings,
		users: Users,
		logout: LogOut
	};
	let { name, filled = false }: { name: keyof typeof icons; filled?: boolean } = $props();
	const Component = $derived(icons[name]);
</script>

<Component
	class="icon"
	size={20}
	strokeWidth={1.75}
	aria-hidden="true"
	fill={filled ? 'currentColor' : 'none'}
/>
