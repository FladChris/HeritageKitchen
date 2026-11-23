import test from 'node:test';
import assert from 'node:assert/strict';
import { keepScreenAwake } from '../src/lib/wake-lock.ts';
const settle = () => new Promise((resolve) => setImmediate(resolve));
function visibility() {
	const events = new EventTarget();
	return {
		visibilityState: 'visible',
		addEventListener: (...args) => events.addEventListener(...args),
		removeEventListener: (...args) => events.removeEventListener(...args),
		change(value) {
			this.visibilityState = value;
			events.dispatchEvent(new Event('visibilitychange'));
		}
	};
}
test('wake lock releases in background, reacquires in foreground and stops on exit', async () => {
	let requests = 0,
		releases = 0;
	const document = visibility();
	const stop = keepScreenAwake(
		async () => {
			requests++;
			return {
				release: async () => {
					releases++;
				}
			};
		},
		document,
		() => assert.fail('should be supported')
	);
	await settle();
	document.change('hidden');
	assert.equal(releases, 1);
	document.change('visible');
	await settle();
	assert.equal(requests, 2);
	stop();
	assert.equal(releases, 2);
	document.change('visible');
	await settle();
	assert.equal(requests, 2);
});
test('late wake-lock response is released after cooking ends', async () => {
	let finish;
	let released = false;
	const stop = keepScreenAwake(
		() =>
			new Promise((resolve) => {
				finish = resolve;
			}),
		visibility(),
		() => {}
	);
	stop();
	finish({
		release: async () => {
			released = true;
		}
	});
	await settle();
	assert.equal(released, true);
});
test('unsupported or denied wake lock announces fallback without blocking cooking', async () => {
	let notices = 0;
	const a = keepScreenAwake(undefined, visibility(), () => {
		notices++;
	});
	a();
	const b = keepScreenAwake(
		async () => {
			throw new Error('denied');
		},
		visibility(),
		() => {
			notices++;
		}
	);
	await settle();
	b();
	assert.equal(notices, 2);
});
