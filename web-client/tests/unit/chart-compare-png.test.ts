// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';

import { chartsFor, totalCharts, type CompareChart } from '../../src/lib/charts/compare-charts';
import {
  chartNumbers,
  compareSourceLine,
  compareSvg,
  drawn,
  markWord,
  pngAll,
  type CompareExportMeta,
} from '../../src/lib/charts/compare-png';
import { exportFileName, type PngEnv } from '../../src/lib/charts/export';
import {
  A,
  B,
  entries,
  header,
  mcell,
  metricOf,
  payloadOf,
  roleCell,
  runValueMetric,
} from './compare-chart-fixtures';

const ids = [A, B];
const run = (id: string, v: string[], over = {}) => runValueMetric(id, ids, v, over);
const meta = (over: Partial<CompareExportMeta> = {}): CompareExportMeta => ({
  entries: entries(),
  project: 'Proj',
  headers: [header(A), header(B)],
  date: '2026-11-13',
  ...over,
});
const payload = payloadOf([
  run('cost.gateway', ['1.5', '2.5']),
  run('cost.harness', ['1.6', '2.4']),
  run('time.machine', ['60', '120']),
  run('time.parked', ['30', '0']),
  run('process.attempts', ['4', '5']),
  run('process.retries', ['1', '0']),
  run('tokens.output', ['10', '20']),
  run('tokens.cache_read', ['5', '6']),
]);
const totals = totalCharts(payload, entries(), 'headline');

describe('compareSvg', () => {
  it('draws the dot plot with both circles, the axis note and the source line', () => {
    const svg = compareSvg(totals[0], meta());
    expect(svg).toContain('axis does not start at zero');
    expect(svg).toContain('data-series="gateway"');
    expect(svg).toContain('data-series="harness"');
    expect(svg).toContain('$1.50 · $1.60');
    expect(svg).toContain(
      'source: ai-orchestrator · project Proj · result v2, v2 per Run · exported 2026-11-13',
    );
    expect(svg).not.toContain('data-follow');
    expect(svg).not.toContain('--color-accent');
    expect(svg).not.toContain('following:');
  });

  it('draws bars, hatch for the second series and the retries share', () => {
    const time = compareSvg(totals[1], meta());
    expect(time).toContain('url(#hatch-2)');
    const attempts = compareSvg(totals[2], meta());
    expect(attempts).toContain('url(#hatch-1)');
    expect(attempts).toContain('label of process.retries');
    expect(compareSvg(totals[3], meta(), 'dark')).toContain('<rect x="0" y="0"');
  });

  it('prints the key of full labels in breakdowns, blind collapsed, and the list-price note', () => {
    const p = payloadOf([
      metricOf('tokens.output', {
        [A]: [roleCell('plan', '3')],
        [B]: [],
      }),
    ]);
    const chart = chartsFor(p, entries(), {
      breakdown: 'role',
      roles: 'declared',
      set: 'headline',
      stepOrder: [],
    })[0];
    const m = meta({
      headers: [
        header(A, { label: 'one', subscription: true }),
        header(B, { label: 'R2', selected_version: null }),
      ],
    });
    const svg = compareSvg(chart, m);
    expect(svg).toContain(`R1 · one · ${A.slice(0, 8)}`);
    expect(svg).toContain(`R2 · ${B.slice(0, 8)}`);
    expect(svg).not.toContain('R2 · R2');
    expect(svg).toContain('no such step in this template');
    expect(svg).toContain('list-price equivalent');
    expect(compareSourceLine(m)).toContain('result v2, values so far per Run');
  });

  it('dots a bar of another method, outlines a partial and words a missing figure', () => {
    const out = run('tokens.output', ['1', '2'], {
      methods_differ: true,
      methods: { [A]: ['m1'], [B]: ['m2'] },
    });
    const [chart] = totalCharts(payloadOf([out]), entries(), 'headline');
    const svg = compareSvg(chart, meta());
    expect(svg).toContain('url(#dots-1)');
    expect(svg).toContain('· m2');
    expect(svg).toContain('≠ methods differ: m1 · m2');
    const dotWord: CompareChart = {
      ...totals[0],
      groups: [
        {
          name: null,
          rows: [
            {
              id: 'x',
              runId: A,
              name: ['R1'],
              marks: [
                { value: null, word: 'not recorded' },
                { value: null, word: '—' },
              ],
            },
          ],
        },
      ],
    };
    expect(compareSvg(dotWord, meta())).toContain('not recorded');
    const outline: CompareChart = {
      ...totals[3],
      groups: [
        {
          name: 'g',
          rows: [
            {
              id: 'x',
              runId: A,
              name: ['R1'],
              marks: [{ value: totals[3].groups[0].rows[0].marks[0].value, outline: true }],
            },
          ],
        },
      ],
    };
    expect(compareSvg(outline, meta())).toContain('· partial');
  });

  it('measures marks: words, outline and empty marks', () => {
    expect(markWord({ value: null, word: 'w' })).toBe('w');
    expect(markWord({ value: null })).toBeNull();
    expect(markWord({ value: mcell({ value_num: null }) as never })).toBeNull();
    expect(drawn({ value: null }, 10, 100)).toBeNull();
    expect(drawn({ value: null, word: 'w' }, 10, 100)).toMatchObject({
      kind: 'missing',
      word: 'w',
    });
    const m = totals[3].groups[0].rows[0].marks[0];
    expect(drawn({ ...m, outline: true }, 100, 100)?.kind).toBe('partial');
    expect(drawn(m, 100, 100)?.kind).toBe('bar');
    expect(chartNumbers(totals[3])).toEqual([10, 20]);
  });
});

function fakeEnv(failAt = -1) {
  const save = vi.fn();
  let n = 0;
  const ctx = { scale: vi.fn(), drawImage: vi.fn() };
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => ctx,
    toBlob: (cb: (b: Blob | null) => void) => cb(new Blob(['x'])),
  };
  const env: PngEnv = {
    loadImage: vi.fn(async () => {
      if (n++ === failAt) throw new Error('decode failed');
      return { width: 820, height: 100, image: {} as CanvasImageSource };
    }),
    createCanvas: () => canvas as unknown as HTMLCanvasElement,
    save,
  };
  return { env, save };
}

describe('pngAll', () => {
  it('writes one file per chart, in order, with the compare file name', async () => {
    const { env, save } = fakeEnv();
    await pngAll(totals, meta(), 'transparent', env);
    expect(save).toHaveBeenCalledTimes(totals.length);
    expect(save.mock.calls.map((c) => c[1])).toEqual(
      totals.map((c) => exportFileName('Proj', 'compare', c.title, '2026-11-13')),
    );
    expect(save.mock.calls[0][1]).toBe('proj-compare-cost-gateway-and-harness-2026-11-13.png');
  });

  it('stops at the first failure', async () => {
    const { env, save } = fakeEnv(1);
    await expect(pngAll(totals, meta(), 'light', env)).rejects.toThrow('decode failed');
    expect(save).toHaveBeenCalledTimes(1);
  });
});
