import { beforeNavigate } from '$app/navigation';

export function guardUnsavedChanges(canLeave: () => boolean): void {
	beforeNavigate(({ cancel, willUnload }) => {
		if (canLeave()) return;
		if (willUnload || !window.confirm('Ungespeicherte Änderungen verwerfen?')) cancel();
	});
}
