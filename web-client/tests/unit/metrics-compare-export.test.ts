import { afterEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import { exportComparison } from '../../src/lib/metrics/compare-export';
import { today } from '../../src/lib/charts/export';
import type { CompareState } from '../../src/lib/metrics/compare';
import { A, B } from './metrics-compare-fixtures';

const state: CompareState = {
  runIds: [A, B],
  versions: { [A]: 1 },
  view: 'table',
  set: 'headline',
  blind: false,
};

const ok = (body: string, name: string | null) => ({
  data: new Blob([body]),
  response: {
    status: 200,
    headers: new Headers(name ? { 'Content-Disposition': `attachment; filename="${name}"` } : {}),
  },
});
const json = JSON.stringify({ runs: [1, 2], catalogue: [1, 2, 3], rows: [] });

afterEach(() => GET.mockReset());

describe('exportComparison', () => {
  it('saves both files under the server names and prints the line', async () => {
    GET.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('csv')
          ? ok('a,b', 'p-compare-2026-11-13.csv')
          : ok(json, 'p-compare-2026-11-13.json'),
      ),
    );
    const save = vi.fn();
    const result = await exportComparison(state, 'p', save);
    expect(result).toEqual({
      ok: true,
      line: 'exported p-compare-2026-11-13.csv and .json · 2 Runs · 3 metrics · run labels included · each description once',
    });
    expect(save.mock.calls.map((c) => c[1])).toEqual([
      'p-compare-2026-11-13.csv',
      'p-compare-2026-11-13.json',
    ]);
  });

  it('sends one query to both reads, with blind when on, and says so', async () => {
    GET.mockImplementation((path: string) =>
      Promise.resolve(path.endsWith('csv') ? ok('x', null) : ok(json, null)),
    );
    const save = vi.fn();
    const result = await exportComparison({ ...state, blind: true, set: 'all' }, 'p', save);
    expect(GET.mock.calls.map((c) => c[0])).toEqual([
      '/metrics/compare.csv',
      '/metrics/compare.json',
    ]);
    for (const call of GET.mock.calls) {
      expect(call[1].params.query).toEqual({ runs: `${A},${B}`, v: `${A}:1`, blind: true });
    }
    expect(result.line).toContain('run labels hidden');
    expect(save.mock.calls.map((c) => c[1])).toEqual([
      `p-compare-${today()}.csv`,
      `p-compare-${today()}.json`,
    ]);
  });

  it('saves nothing when the csv read fails', async () => {
    GET.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('csv') ? { error: {}, response: { status: 500 } } : ok(json, null),
      ),
    );
    const save = vi.fn();
    const result = await exportComparison(state, 'p', save);
    expect(result).toEqual({
      ok: false,
      line: 'export failed · GET /api/metrics/compare.csv · 500',
    });
    expect(save).not.toHaveBeenCalled();
  });

  it('reports a failing json read by its own path', async () => {
    GET.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('csv') ? ok('x', null) : { error: {}, response: { status: 422 } },
      ),
    );
    const save = vi.fn();
    expect((await exportComparison(state, 'p', save)).line).toBe(
      'export failed · GET /api/metrics/compare.json · 422',
    );
    expect(save).not.toHaveBeenCalled();
  });

  it('reports network for a rejected read', async () => {
    GET.mockImplementation((path: string) =>
      path.endsWith('csv') ? Promise.reject(new Error('down')) : Promise.resolve(ok(json, null)),
    );
    const save = vi.fn();
    const result = await exportComparison(state, 'p', save);
    expect(result).toEqual({
      ok: false,
      line: 'export failed · GET /api/metrics/compare.csv · network',
    });
    expect(save).not.toHaveBeenCalled();
  });

  it('uses the browser save by default', async () => {
    GET.mockResolvedValue({ error: {}, response: { status: 500 } });
    expect((await exportComparison(state, 'p')).ok).toBe(false);
  });
});
