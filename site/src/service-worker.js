/// <reference types="@sveltejs/kit" />
import { immutable, assets } from '$app/manifest';
import { version } from '$app/env';
import { clearLoadedSnapshot, serveOffline } from '$lib/offline/serve';
import { deviceSession, idbStorage } from '$lib/offline/idb-storage';
import { OFFLINE_WIPE_MESSAGE } from '$lib/offline/wipe-channel';

// Cache the complete app shell, including all locally bundled fonts. Recipes
// and uploaded photos are always fetched from the server first; only when it is
// unreachable are they answered from the offline copy that a signed-in, approved
// account synced explicitly. Without such a copy nothing is served.
const CACHE_PREFIX = 'heritagekitchen-shell-';
const CACHE_NAME = `${CACHE_PREFIX}${version}`;
const SHELL = new URL('index.html', self.registration.scope).href;
const ASSETS = [
	...new Set([
		SHELL,
		...[...immutable, ...assets].map((entry) => new URL(entry.path, self.registration.scope).href)
	])
];

self.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE_NAME)
			.then((cache) => cache.addAll(ASSETS))
			.then(() => self.skipWaiting())
	);
});
let startupPurge;
function resumeInterruptedPurge() {
	startupPurge ??= deviceSession.resumePurge().catch(() => {
		startupPurge = undefined;
	});
	return startupPurge;
}

self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) =>
				Promise.all(
					keys
						.filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
						.map((key) => caches.delete(key))
				)
			)
			.then(resumeInterruptedPurge)
			.then(() => self.clients.claim())
	);
});
async function notifyWipe(except) {
	clearLoadedSnapshot();
	const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
	for (const client of clients) {
		if (client.id !== except) client.postMessage(OFFLINE_WIPE_MESSAGE);
	}
}

let authChange = Promise.resolve();
let loginAbort = new AbortController();
let logoutRequest;

async function isAuthDenial(response) {
	if (response.status !== 401 && response.status !== 403) return false;
	const contentType = response.headers.get('Content-Type')?.split(';', 1)[0].trim().toLowerCase();
	if (contentType !== 'application/json') return false;
	const body = await response
		.clone()
		.json()
		.catch(() => null);
	return typeof body?.detail === 'string' && body.detail.trim().length > 0;
}
async function finishLogout(binding, request = '/api/auth/logout') {
	if (!binding?.pendingLogout) return;
	logoutRequest ??= fetch(request, {
		method: 'POST',
		credentials: 'same-origin',
		signal: AbortSignal.timeout(8000)
	})
		.catch(() => null)
		.finally(() => {
			logoutRequest = undefined;
		});
	const response = await logoutRequest;
	if (response && (response.status === 204 || (await isAuthDenial(response))))
		await deviceSession.finishLogout(binding.epoch);
	return response;
}

let authRevision = 0;
let offlineBlocked = false;
async function applyIdentity(response, epoch, mayBind, revision, except) {
	if (epoch === undefined || revision !== authRevision) return;
	let wiped = false;
	if (response.status === 401 || response.status === 403) {
		if (!(await isAuthDenial(response)) || revision !== authRevision) return;
		wiped = await deviceSession.revoke({ epoch });
	} else if (response.ok) {
		const notJson = Symbol('not-json');
		const user = await response
			.clone()
			.json()
			.catch(() => notJson);
		// A captive portal or proxy page says nothing about the account.
		if (user === notJson || revision !== authRevision) return;
		const eligible =
			Number.isSafeInteger(user?.id) && user.is_active === true && user.pending_approval === false;
		wiped = eligible
			? await deviceSession.confirm(user.id, mayBind, epoch)
			: await deviceSession.revoke({ epoch });
	} else {
		return;
	}
	offlineBlocked = false;
	if (wiped) await notifyWipe(except);
}

async function identity(request, mayBind, clientId) {
	await authChange;
	const revision = authRevision;
	const binding = await deviceSession.binding().catch(() => undefined);
	if (binding?.pendingLogout) {
		const response = await finishLogout(binding);
		if (!response) throw new TypeError('Server unreachable');
		return new Response(null, { status: 401 });
	}
	const response = await fetch(request, {
		cache: 'no-store',
		...(typeof request === 'string'
			? { credentials: 'same-origin', signal: AbortSignal.timeout(8000) }
			: {})
	});
	try {
		await applyIdentity(
			response,
			binding === undefined ? undefined : (binding?.epoch ?? ''),
			mayBind,
			revision,
			clientId
		);
	} catch {
		offlineBlocked = true;
	}
	return response;
}

let identityCheck;
function checkKnownAccount(clientId) {
	identityCheck ??= (async () => {
		const binding = await deviceSession.binding();
		if (binding?.userId !== undefined || binding?.purging || binding?.pendingLogout)
			await identity(new URL('/api/auth/me', self.location.origin).href, false, clientId);
	})()
		.catch(() => undefined)
		.finally(() => {
			identityCheck = undefined;
		});
	return identityCheck;
}

async function fetchCookbook(request, clientId) {
	if (request.credentials === 'omit') return fetch(request);
	await authChange;
	const binding = await deviceSession.binding().catch(() => null);
	if (binding?.pendingLogout) {
		await finishLogout(binding);
		return fetch(request, { credentials: 'omit' });
	}
	const response = await fetch(request);
	if (!request.headers.has('X-Offline-Sync')) await checkKnownAccount(clientId);
	return response;
}

self.addEventListener('fetch', (event) => {
	const { request } = event;
	const url = new URL(request.url);
	if (url.origin !== self.location.origin) return;
	event.waitUntil(resumeInterruptedPurge());
	const clientId = event.clientId || event.resultingClientId;
	const logout = url.pathname === '/api/auth/logout';
	const login = url.pathname === '/api/auth/login';
	if (request.method === 'POST' && logout) {
		++authRevision;
		loginAbort.abort();
		loginAbort = new AbortController();
		const localLogout = (async () => {
			await deviceSession.revoke({ logout: true });
			await notifyWipe(clientId);
			return deviceSession.binding();
		})();
		authChange = localLogout
			.then((binding) => finishLogout(binding, request))
			.catch(() => undefined);
		event.waitUntil(authChange);
		event.respondWith(
			localLogout.then(
				() =>
					new Response(null, {
						status: 204,
						headers: { 'X-Local-Logout': '1' }
					})
			)
		);
		return;
	}
	if (request.method === 'POST' && login) {
		const signal = request.signal
			? AbortSignal.any([request.signal, loginAbort.signal])
			: loginAbort.signal;
		const change = authChange.then(async () => {
			signal.throwIfAborted();
			const revision = ++authRevision;
			const binding = await deviceSession.binding().catch(() => undefined);
			if (binding?.pendingLogout) await finishLogout(binding);
			signal.throwIfAborted();
			const response = await fetch(request, { signal });
			signal.throwIfAborted();
			if (response.ok) {
				try {
					await applyIdentity(response, await deviceSession.epoch(), false, revision, clientId);
				} catch {
					offlineBlocked = true;
				}
				// A successful login replaces the previous cookie.
				if (binding?.pendingLogout) await deviceSession.finishLogout(binding.epoch);
			}
			return response;
		});
		authChange = change.then(
			() => undefined,
			() => undefined
		);
		event.respondWith(change);
		return;
	}
	if (request.method !== 'GET') {
		if (url.pathname.startsWith('/api/')) event.respondWith(fetchCookbook(request, clientId));
		return;
	}
	if (url.pathname.startsWith('/api') || url.pathname.startsWith('/media')) {
		const readable =
			request.credentials !== 'omit' &&
			!request.headers.has('X-Offline-Sync') &&
			(request.headers.has('X-Offline-Read') ||
				(url.pathname.startsWith('/media/') && url.searchParams.get('heritagekitchen-offline') === '1'));
		const checkIdentity = url.pathname === '/api/auth/me' && request.credentials !== 'omit';
		const network = checkIdentity
			? identity(request, request.headers.has('X-Offline-Read'), clientId)
			: fetchCookbook(request, clientId);
		event.respondWith(
			network.catch(async (error) => {
				const binding =
					readable && !offlineBlocked ? await deviceSession.binding().catch(() => null) : null;
				const owner = binding?.purging ? undefined : binding?.userId;
				if (owner === undefined) throw error;
				const stored = await serveOffline(url, idbStorage, owner).catch(() => null);
				if (stored && (await deviceSession.binding().catch(() => null))?.epoch === binding?.epoch)
					return stored;
				throw error;
			})
		);
		return;
	}
	if (request.mode === 'navigate') {
		event.respondWith(
			fetch(request)
				.then(async (response) => {
					await checkKnownAccount(clientId);
					return response;
				})
				.catch(async () => (await caches.match(SHELL)) ?? Response.error())
		);
		return;
	}
	if (!ASSETS.includes(url.href)) return;
	event.respondWith(
		caches.match(request).then(async (cached) => {
			if (cached) return cached;
			const response = await fetch(request);
			if (response.ok) {
				const copy = response.clone();
				event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)));
			}
			return response;
		})
	);
});
