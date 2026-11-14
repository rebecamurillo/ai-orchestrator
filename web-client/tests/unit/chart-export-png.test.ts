// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { browserEnv, writePng, type PngEnv } from '../../src/lib/charts/export';

const SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="820" height="100"/>';

function fakeEnv(over: Partial<PngEnv> = {}, blob: Blob | null = new Blob(['x'])) {
  const calls: string[] = [];
  const ctx = {
    scale: vi.fn((x: number, y: number) => calls.push(`scale ${x} ${y}`)),
    drawImage: vi.fn(() => calls.push('draw')),
  };
  const canvas = {
    width: 0,
    height: 0,
    getContext: vi.fn(() => ctx),
    toBlob: vi.fn((cb: (b: Blob | null) => void, type: string) => {
      calls.push(`toBlob ${type}`);
      cb(blob);
    }),
  };
  const save = vi.fn();
  const image = {} as CanvasImageSource;
  const env: PngEnv = {
    loadImage: vi.fn(async () => ({ width: 820, height: 100, image })),
    createCanvas: () => canvas as unknown as HTMLCanvasElement,
    save,
    ...over,
  };
  return { env, canvas, ctx, save, calls, image };
}

describe('writePng (AC5)', () => {
  it('draws at 2x on a 1640 px canvas and saves a PNG blob', async () => {
    const { env, canvas, ctx, save, calls, image } = fakeEnv();
    await writePng(SVG, 'a.png', env);
    expect(canvas.width).toBe(1640);
    expect(canvas.height).toBe(200);
    expect(calls).toEqual(['scale 2 2', 'draw', 'toBlob image/png']);
    expect(ctx.drawImage).toHaveBeenCalledWith(image, 0, 0);
    expect(save).toHaveBeenCalledWith(expect.any(Blob), 'a.png');
    expect(vi.mocked(env.loadImage).mock.calls[0][0]).toMatch(/^data:image\/svg\+xml/);
  });

  it('rejects with the reason, without retry, when the image fails, the blob is null or no context', async () => {
    const bad = fakeEnv({
      loadImage: vi.fn(async () => Promise.reject(new Error('decode failed'))),
    });
    await expect(writePng(SVG, 'a.png', bad.env)).rejects.toThrow('decode failed');
    expect(bad.env.loadImage).toHaveBeenCalledTimes(1);
    const nonError = fakeEnv({ loadImage: vi.fn(async () => Promise.reject('plain')) });
    await expect(writePng(SVG, 'a.png', nonError.env)).rejects.toThrow('plain');
    const empty = fakeEnv({}, null);
    await expect(writePng(SVG, 'a.png', empty.env)).rejects.toThrow('canvas produced no PNG');
    expect(empty.save).not.toHaveBeenCalled();
    const noCtx = fakeEnv();
    noCtx.canvas.getContext.mockReturnValue(null as never);
    await expect(writePng(SVG, 'a.png', noCtx.env)).rejects.toThrow('canvas has no 2d context');
  });
});

describe('browserEnv', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('loads an image after decode and reports its natural size', async () => {
    class Img {
      naturalWidth = 820;
      naturalHeight = 90;
      src = '';
      decode = vi.fn(async () => undefined);
    }
    vi.stubGlobal('Image', Img);
    const loaded = await browserEnv.loadImage('data:x');
    expect(loaded.width).toBe(820);
    expect(loaded.height).toBe(90);
  });

  it('creates a canvas and saves through a revoked object URL anchor', () => {
    expect(browserEnv.createCanvas().tagName).toBe('CANVAS');
    const create = vi.fn(() => 'blob:1');
    const revoke = vi.fn();
    vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: revoke });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    browserEnv.save(new Blob(['x']), 'f.png');
    expect(create).toHaveBeenCalled();
    expect(click).toHaveBeenCalledTimes(1);
    expect(revoke).toHaveBeenCalledWith('blob:1');
    expect(document.querySelector('a[download]')).toBeNull();
  });
});
