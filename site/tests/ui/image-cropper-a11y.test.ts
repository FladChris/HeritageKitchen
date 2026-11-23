import { beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import ImageCropper from '../../src/lib/components/ImageCropper.svelte';

const crop = vi.hoisted(() => ({
  getCropBoxData: vi.fn(() => ({ left: 20, top: 30, width: 100, height: 100 })),
  setCropBoxData: vi.fn(),
  setAspectRatio: vi.fn(),
  destroy: vi.fn()
}));

vi.mock('cropperjs', () => ({
  default: vi.fn().mockImplementation(function () { return crop; })
}));

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: () => 'blob:test-image' });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
});

test('image cropping is an accessible native dialog with keyboard-operable adjustments', async () => {
  const onCancel = vi.fn();
  render(ImageCropper, {
    file: new File(['test'], 'foto.png', { type: 'image/png' }),
    onDone: vi.fn(),
    onCancel
  });
  const dialog = screen.getByRole('dialog', { name: 'Bild zuschneiden' }) as HTMLDialogElement;
  expect(dialog.open).toBe(true);
  const frame = screen.getByRole('application', { name: 'Zuschnittrahmen' });
  frame.focus();
  expect(document.activeElement).toBe(frame);
  await fireEvent.keyDown(frame, { key: 'ArrowLeft' });
  expect(crop.setCropBoxData).toHaveBeenLastCalledWith({ left: 10, top: 30 });
  await fireEvent.keyDown(frame, { key: 'ArrowDown', shiftKey: true });
  expect(crop.setCropBoxData).toHaveBeenLastCalledWith({ width: 100, height: 110 });
  await fireEvent.click(screen.getByRole('button', { name: '1:1' }));
  await fireEvent.keyDown(frame, { key: 'ArrowUp', shiftKey: true });
  expect(crop.setCropBoxData).toHaveBeenLastCalledWith({ width: 90, height: 90 });
  await fireEvent(dialog, new Event('cancel', { cancelable: true }));
  expect(onCancel).toHaveBeenCalledOnce();
});
