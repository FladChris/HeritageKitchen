import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
test('the installed shell restores a verified device offline and revokes it on account changes', async () => {
	const events = {},
		cached = new Map();
	const origin = 'https://kitchen.test';
	let online = true;
	let collection = new Map();
	let denied = false;
	let pendingLogout = false;
	let rejectLogout = false;
	let identity = { id: 7, is_active: true, pending_approval: false };
	let portalStatus;
	let interruptedPurge = false;
	const notifications = [];
	let hangingLoginStarted;
	let loginSignal;
	let hangLogin = false;
	let hangingLogoutStarted;
	let hangLogout = false;
	let boundAccount;
	let revision = 0;
	const network = async (request, options) => {
		const url = typeof request === 'string' ? new URL(request, origin).href : request.url;
		if (!online) throw new Error('offline');
		if (url.endsWith('/api/auth/login') && hangLogin) {
			loginSignal = options?.signal;
			hangingLoginStarted();
			return new Promise(() => {});
		}
		if (url.endsWith('/api/auth/logout')) {
			if (hangLogout) {
				hangingLogoutStarted();
				return new Promise(() => {});
			}
			if (rejectLogout) return new Response(null, { status: 503 });
			denied = true;
			return new Response(null, { status: 204 });
		}
		if (url.endsWith('/api/favorites') && options?.credentials === 'omit')
			return new Response('Signed out', { status: 401 });
		if (denied && url.endsWith('/api/auth/me'))
			return Response.json({ detail: 'Not authenticated.' }, { status: 401 });
		if (url.endsWith('/api/auth/me'))
			return portalStatus
				? new Response('<html>Login</html>', {
						status: portalStatus,
						headers: { 'Content-Type': 'text/html' }
					})
				: Response.json(identity);
		return new Response(`Online: ${url}`);
	};
	const manifest = JSON.parse(
		readFileSync(new URL('../static/manifest.webmanifest', import.meta.url), 'utf8')
	);
	assert.equal(manifest.start_url, '/');
	assert.equal(manifest.scope, '/');
	assert.equal(manifest.display, 'standalone');
	const fonts = [
		'/_app/fonts/fraunces.woff2',
		'/_app/fonts/inter.woff2',
		'/_app/fonts/serif.woff2'
	];
	const assets = ['/manifest.webmanifest', ...manifest.icons.map(({ src }) => src)];
	const source = readFileSync(new URL('../src/service-worker.js', import.meta.url), 'utf8').replace(
		/^import .*;$/gm,
		''
	);
	const context = {
		URL,
		AbortSignal,
		AbortController,
		Response,
		immutable: fonts.map((path) => ({ path })),
		assets: assets.map((path) => ({ path })),
		version: 'test',
		OFFLINE_WIPE_MESSAGE: 'offline-data-wiped',
		idbStorage: {},
		clearLoadedSnapshot() {},
		deviceSession: {
			resumePurge: async () => {
				if (interruptedPurge) {
					collection.clear();
					interruptedPurge = false;
				}
			},
			binding: async () => ({ userId: boundAccount, epoch: revision, pendingLogout }),
			finishLogout: async () => {
				pendingLogout = false;
			},
			epoch: async () => revision,
			confirm: async (account, mayBind, epoch) => {
				if (epoch !== revision || account === boundAccount) return;
				collection.clear();
				boundAccount = mayBind ? account : undefined;
				revision++;
				return true;
			},
			revoke: async ({ epoch, logout } = {}) => {
				if (epoch !== undefined && epoch !== revision) return;
				collection.clear();
				pendingLogout ||= !!logout;
				const hadAccount = boundAccount !== undefined;
				boundAccount = undefined;
				revision++;
				return hadAccount;
			}
		},
		serveOffline: async ({ pathname }, _storage, account) =>
			collection.has(account)
				? pathname === '/api/settings'
					? Response.json({ cookbook_name: 'Familienrezepte' }, { headers: { 'X-Offline': '1' } })
					: new Response('Offline: ' + pathname, { headers: { 'X-Offline': '1' } })
				: null,
		self: {
			registration: { scope: `${origin}/` },
			location: { origin },
			clients: {
				claim() {},
				async matchAll() {
					return ['owner', 'other'].map((id) => ({
						id,
						postMessage(message) {
							notifications.push([id, message]);
						}
					}));
				}
			},
			skipWaiting() {},
			addEventListener(name, handler) {
				events[name] = handler;
			}
		},
		caches: {
			keys: async () => [...cached.keys()],
			async open() {
				return {
					async addAll(paths) {
						for (const url of paths) cached.set(url, await network({ url }));
					},
					async put(request, response) {
						cached.set(request.url, response);
					}
				};
			},
			async match(request) {
				return cached.get(typeof request === 'string' ? request : request.url)?.clone();
			}
		},
		fetch: network
	};
	const startWorker = () => vm.runInNewContext(source, { ...context });
	startWorker();
	let installed;
	events.install({
		waitUntil(promise) {
			installed = promise;
		}
	});
	await installed;
	const shell = ['/index.html', ...fonts, ...assets].map((path) => `${origin}${path}`).sort();
	assert.deepEqual([...cached.keys()].sort(), shell);
	const dispatch = (
		path,
		mode = 'cors',
		headers = new Headers(),
		method = 'GET',
		clientId = 'owner'
	) => {
		const request = { url: `${origin}${path}`, method, mode, headers };
		const pending = [];
		let response;
		events.fetch({
			clientId,
			request,
			respondWith(promise) {
				response = promise;
			},
			waitUntil(promise) {
				pending.push(promise);
			}
		});
		return { response: response ?? network(request), pending };
	};
	const requestContent = async (...args) => {
		const { response, pending } = dispatch(...args);
		const result = await response;
		await Promise.all(pending);
		return result.text();
	};
	const contentPaths = [
		'/api/categories',
		'/api/recipes?category_id=1',
		'/api/recipes/3',
		'/api/recipes/3/pdf',
		'/api/recipe-images/1',
		'/media/recipe-images/recipe.jpg',
		'/media/recipe-images/category.jpg',
		'/uploads/photo.jpg'
	];
	assert.equal(await requestContent('/recipes/3', 'navigate'), `Online: ${origin}/recipes/3`);
	for (const path of contentPaths) {
		assert.equal(await requestContent(path), `Online: ${origin}${path}`);
	}
	assert.deepEqual([...cached.keys()].sort(), shell);

	online = false;
	assert.equal(await requestContent('/recipes/3', 'navigate'), `Online: ${origin}/index.html`);
	for (const path of contentPaths) {
		await assert.rejects(requestContent(path), /offline/);
	}

	const read = new Headers({ 'X-Offline-Read': '1' });
	const sync = new Headers({ 'X-Offline-Sync': '1', 'X-Offline-Read': '1' });
	await assert.rejects(requestContent('/api/recipes/5', 'cors', read, 'GET', 'unbound'), /offline/);
	online = true;
	await requestContent('/api/auth/me', 'cors', read);
	collection.set(7, ['recipes', 'images', 'comments', 'favorites', 'sorts']);
	online = false;
	const cold = 'new-client-after-app-restart';
	assert.equal(
		await requestContent('/recipes/5', 'navigate', new Headers(), 'GET', cold),
		`Online: ${origin}/index.html`
	);
	assert.deepEqual(JSON.parse(await requestContent('/api/settings', 'cors', read, 'GET', cold)), {
		cookbook_name: 'Familienrezepte'
	});
	for (const [path, headers] of [
		['/api/auth/me', read],
		['/api/recipes/5', read],
		['/api/favorites', read],
		['/media/recipe-images/recipe.jpg?heritagekitchen-offline=1', new Headers()]
	]) {
		assert.match(await requestContent(path, 'cors', headers, 'GET', cold), /^Offline:/);
	}
	await assert.rejects(
		requestContent('/api/recipes/5', 'cors', new Headers(), 'GET', cold),
		/offline/
	);
	await assert.rejects(requestContent('/api/recipes/5', 'cors', sync), /offline/);
	await assert.rejects(requestContent('/api/recipes/5', 'cors', read, 'PUT'), /offline/);

	for (const change of ['deactivation', 'deletion', 'password revoke', 'expiry']) {
		online = true;
		denied = false;
		await requestContent('/api/auth/me', 'cors', read);
		collection.set(7, ['recipes', 'images', 'comments', 'favorites', 'sorts']);
		online = false;
		denied = true;
		assert.match(await requestContent('/api/recipes/5', 'cors', read), /^Offline:/, change);
		assert.equal(collection.size, 1, change);
		await assert.rejects(requestContent('/api/favorites', 'cors', read, 'POST'), /offline/);
		online = true;
		// Public reads may still succeed after a server-side revocation.
		await requestContent('/api/recipes/5', 'cors', read);
		assert.equal(collection.size, 0, change);
		online = false;
		await assert.rejects(requestContent('/api/recipes/5', 'cors', read), /offline/);
	}

	for (const approved of [false, true]) {
		online = true;
		denied = false;
		identity = { id: 7, is_active: true, pending_approval: false };
		await requestContent('/api/auth/me', 'cors', read);
		collection.set(7, ['Lena?s recipes and favorites']);
		identity = { ...identity, id: 8, pending_approval: !approved };
		await requestContent('/api/auth/me', 'cors', read);
		assert.equal(collection.size, 0);
		assert.equal(boundAccount, approved ? 8 : undefined);
		if (approved) collection.set(8, ['Tim?s recipes and favorites']);
		online = false;
		if (approved) assert.match(await requestContent('/api/favorites', 'cors', read), /^Offline:/);
		else await assert.rejects(requestContent('/api/favorites', 'cors', read), /offline/);
	}
	online = true;
	identity = { id: 7, is_active: true, pending_approval: false };
	await requestContent('/api/auth/me', 'cors', read);
	collection.set(7, ['recipes', 'images', 'comments', 'favorites', 'sorts']);
	online = false;
	await requestContent('/api/auth/logout', 'cors', new Headers(), 'POST', 'other');
	assert.equal(collection.size, 0);
	assert.deepEqual([...cached.keys()].sort(), shell);
	await assert.rejects(requestContent('/api/recipes/5', 'cors', read), /offline/);
	online = true;
	rejectLogout = true;
	assert.equal(await requestContent('/api/favorites', 'cors', read), 'Signed out');
	assert.equal(pendingLogout, true);
	rejectLogout = false;
	await requestContent('/api/auth/me', 'cors', read);
	assert.equal(pendingLogout, false);
	assert.equal(boundAccount, undefined);

	online = true;
	denied = false;
	identity = { id: 7, is_active: true, pending_approval: false };
	await requestContent('/api/auth/me', 'cors', read);
	collection.set(7, ['Lena']);
	for (const status of [200, 401, 403, 511]) {
		portalStatus = status;
		await requestContent('/api/auth/me', 'cors', new Headers(), 'GET', 'other');
		assert.equal(boundAccount, 7, `HTML ${status}`);
		assert.equal(collection.size, 1, `HTML ${status}`);
	}
	portalStatus = undefined;
	denied = true;
	notifications.length = 0;
	await requestContent('/api/auth/me', 'cors', new Headers(), 'GET', 'other');
	assert.equal(collection.size, 0);
	assert.deepEqual(notifications, [['owner', 'offline-data-wiped']]);
	denied = false;
	await requestContent('/api/auth/me', 'cors');
	assert.equal(boundAccount, undefined);
	await requestContent('/api/auth/me', 'cors', read);
	identity = { ...identity, id: 8 };
	await requestContent('/api/auth/me', 'cors', read);
	assert.equal(boundAccount, 8);
	online = false;
	await assert.rejects(requestContent('/api/recipes/5', 'cors', read, 'GET', cold), /offline/);

	online = true;
	denied = true;
	notifications.length = 0;
	await requestContent('/api/recipes/5', 'cors', read);
	assert.deepEqual(notifications, [['other', 'offline-data-wiped']]);

	// Restart the worker with unfinished cache deletion and no server contact.
	online = false;
	for (const activation of [true, false]) {
		collection.set(7, ['orphaned images']);
		interruptedPurge = true;
		startWorker();
		if (activation) {
			let activated;
			events.activate({
				waitUntil: (promise) => {
					activated = promise;
				}
			});
			await activated;
		} else {
			await requestContent('/recipes/5', 'navigate');
		}
		assert.equal(interruptedPurge, false);
		assert.equal(collection.size, 0);
	}

	online = true;
	denied = false;
	await requestContent('/api/auth/me', 'cors', read);
	collection.set(8, ['Tim']);
	hangLogin = true;
	hangLogout = true;
	const loginStarted = new Promise((resolve) => {
		hangingLoginStarted = resolve;
	});
	const logoutStarted = new Promise((resolve) => {
		hangingLogoutStarted = resolve;
	});
	dispatch('/api/auth/login', 'cors', new Headers(), 'POST');
	await loginStarted;
	const logout = dispatch('/api/auth/logout', 'cors', new Headers(), 'POST');
	let deadline;
	const timeout = new Promise((_, reject) => {
		deadline = setTimeout(() => reject(new Error('Local logout blocked')), 1000);
	});
	const local = await Promise.race([logout.response, timeout]).finally(() =>
		clearTimeout(deadline)
	);
	assert.equal(local.status, 204);
	assert.equal(collection.size, 0);
	assert.equal(loginSignal?.aborted, true);
	await logoutStarted;
});
