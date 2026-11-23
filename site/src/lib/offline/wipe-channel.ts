export const OFFLINE_WIPE_MESSAGE = 'offline-data-wiped';

let channel: BroadcastChannel | undefined;

export function getOfflineWipeChannel() {
	// Reuse the receiving channel when sending so the initiating tab cannot
	// receive its own notification.
	if (typeof BroadcastChannel !== 'undefined')
		channel ??= new BroadcastChannel(OFFLINE_WIPE_MESSAGE);
	return channel;
}
