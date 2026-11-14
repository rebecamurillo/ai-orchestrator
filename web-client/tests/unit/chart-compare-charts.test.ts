import { describe, expect, it } from 'vitest';

import {
  asValue,
  chartsFor,
  familyCharts,
  familyValue,
  modelCharts,
  rangeTicks,
  roleCharts,
  roleOrderAcross,
  totalCharts,
} from '../../src/lib/charts/compare-charts';
import { NO_MODEL_GATEWAY } from '../../src/lib/charts/run-charts';
import {
  A,
  B,
  attemptCell,
  entries,
  header,
  mcell,
  metricOf,
  payloadOf,
  roleCell,
  runValueMetric,
} from './compare-chart-fixtures';
import type { CompareMetric } from './metrics-compare-fixtures';

const ids = [A, B];
const run = (id: string, v: string[]) => runValueMetric(id, ids, v);

describe('totalCharts', () => {
  const payload = payloadOf([
    run('tokens.output', ['10', '20']),
    run('cost.gateway', ['1.5', '2.5']),
    run('cost.harness', ['1.6', '2.4']),
    run('time.machine', ['60', '120']),
    run('time.parked', ['30', '0']),
    run('process.attempts', ['4', '5']),
    run('process.retries', ['1', '0']),
    run('tokens.cache_read', ['5', '6']),
    run('tokens.cache_hit_share', ['0.5', '0.6']),
    run('activity.messages_session', ['7', '8']),
    run('activity.messages_subagents', ['1', '2']),
    run('activity.pauses_over_cache_lifetime', ['0', '1']),
    run('tokens.input', ['1', '1']),
  ]);

  it('orders by the primary metric position and keeps the headline set', () => {
    const charts = totalCharts(payload, entries(), 'headline');
    expect(charts.map((c) => c.title)).toEqual([
      'output tokens',
      'cost · gateway and harness',
      'machine time · waiting on you',
      'attempts · of which retries',
      'cache read tokens',
    ]);
  });

  it('adds the ALL charts and marks the dot plot axis', () => {
    const charts = totalCharts(payload, entries(), 'all');
    expect(charts).toHaveLength(8);
    const dot = charts.find((c) => c.kind === 'dot')!;
    expect(dot.axisFromZero).toBe(false);
    expect(dot.context.at(-1)).toBe('US dollars · axis does not start at zero');
    expect(charts.filter((c) => c.axisFromZero)).toHaveLength(7);
    expect(charts.find((c) => c.title.startsWith('machine'))!.second).toBe('hatch');
  });

  it('drops a chart without a catalogue entry or without its primary metric', () => {
    const charts = totalCharts(payload, entries(['tokens.output']), 'all');
    expect(charts.map((c) => c.title)).toEqual(['output tokens']);
    expect(totalCharts(payloadOf([run('tokens.input', ['1', '1'])]), entries(), 'all')).toEqual([]);
  });

  it('draws one row per Run in selection order with names and shared words', () => {
    const p = {
      ...payload,
      runs: [header(A, { label: 'fam x opus' }), header(B, { label: 'fam x sonnet' })],
    };
    const chart = totalCharts(p, entries(), 'headline')[0];
    expect(chart.context[0]).toBe('fam x');
    expect(chart.groups).toHaveLength(1);
    expect(chart.groups[0].rows.map((r) => r.runId)).toEqual(ids);
    expect(chart.groups[0].rows[0].name[0]).toBe('opus');
    expect(chart.groups[0].rows[0].marks[0].value?.value_num).toBe('10');
  });

  it('attaches the retries share and keeps pair marks', () => {
    const charts = totalCharts(payload, entries(), 'headline');
    const attempts = charts.find((c) => c.metricIds[0] === 'process.attempts')!;
    expect(attempts.groups[0].rows[0].marks[0].share?.value_num).toBe('1');
    expect(attempts.groups[0].rows[1].marks[0].share?.value_num).toBe('0');
    const time = charts.find((c) => c.kind === 'pair')!;
    expect(time.groups[0].rows[0].marks[1]?.value?.value_num).toBe('30');
  });

  it('reads a missing cell as a dash and a null figure as its word', () => {
    const p = payloadOf([
      metricOf('tokens.output', {
        [A]: [mcell({ value_num: null, missing: 'not recorded' })],
      }),
      runValueMetric('time.machine', [A, B], ['1', '2']),
    ]);
    const chart = totalCharts(p, entries(), 'headline')[0];
    expect(chart.groups[0].rows[0].marks[0]).toEqual({ value: null, word: 'not recorded' });
    expect(chart.groups[0].rows[1].marks[0]).toEqual({ value: null, word: '—' });
    const pair = totalCharts(p, entries(), 'headline').find((c) => c.kind === 'pair')!;
    expect(pair.groups[0].rows[0].marks[1]).toEqual({ value: null, word: '—' });
  });

  it('flags differing methods and dots the other Run', () => {
    const output = runValueMetric('tokens.output', ids, ['1', '2'], {
      methods_differ: true,
      methods: { [A]: ['m2', 'm1'], [B]: ['m3'] },
    });
    const chart = totalCharts(payloadOf([output]), entries(), 'headline')[0];
    expect(chart.flag).toBe('≠ methods differ: m1 · m2 · m3');
    expect(chart.groups[0].rows[0].marks[0].dotted).toBeUndefined();
    expect(chart.groups[0].rows[1].marks[0].dotted).toBe('m3');
    const same = runValueMetric('tokens.output', ids, ['1', '2']);
    expect(totalCharts(payloadOf([same]), entries(), 'headline')[0].flag).toBeNull();
  });
});

describe('roleOrderAcross and roleCharts', () => {
  const roleMetric = (id: string, a: string[], b: string[]): CompareMetric =>
    metricOf(id, {
      [A]: [
        ...a.map((r) => roleCell(r, '3')),
        attemptCell('plan', 's1', 1),
        attemptCell('implement', 's2', 1),
        attemptCell('review', 's3', 1),
      ],
      [B]: b.map((r) => roleCell(r, '4')),
    });
  const payload = payloadOf([
    roleMetric('tokens.output', ['review', 'plan', 'implement'], ['plan', 'implement']),
    roleMetric('tokens.cache_read', ['plan', 'implement', 'review'], ['plan', 'implement']),
    roleMetric('cost.gateway', ['plan', 'implement', 'review'], ['plan', 'implement']),
    roleMetric('cost.harness', ['plan', 'implement', 'review'], ['plan', 'implement']),
  ]);

  it('follows the step order, then roles only other Runs have', () => {
    const order = roleOrderAcross(payload, 'tokens.output', ['s1', 's2', 's3']);
    expect(order).toEqual(['plan', 'implement', 'review']);
    const p = payloadOf([
      metricOf('tokens.output', {
        [A]: [roleCell('x', '1')],
        [B]: [roleCell('x', '1'), roleCell('y', '2')],
      }),
    ]);
    expect(roleOrderAcross(p, 'tokens.output', [])).toEqual(['x', 'y']);
    expect(roleOrderAcross({ ...p, runs: [] }, 'tokens.output', [])).toEqual([]);
  });

  it('builds three charts with a no-such-step row and no mark for the missing role', () => {
    const charts = roleCharts(payload, entries(), ['s1', 's2', 's3']);
    expect(charts.map((c) => c.title)).toEqual([
      'cost by role · gateway and harness',
      'output tokens by role',
      'cache read tokens by role',
    ]);
    const out = charts[1];
    expect(out.groups.map((g) => g.name)).toEqual(['plan', 'implement', 'review']);
    const review = out.groups[2].rows;
    expect(review.map((r) => r.name)).toEqual([['R1'], ['R2']]);
    expect(review[1].marks[0]).toEqual({ value: null, word: 'no such step in this template' });
    expect(review[0].marks[0].value?.value_num).toBe('3');
    expect(charts[0].kind).toBe('pair');
  });

  it('drops charts with no role cell and tolerates a pair with one cost metric missing', () => {
    const p = payloadOf([run('tokens.output', ['1', '2'])]);
    expect(roleCharts(p, entries(), [])).toEqual([]);
    const half = payloadOf([
      metricOf('cost.gateway', { [A]: [roleCell('plan', '1')], [B]: [] }),
      metricOf('cost.harness', { [A]: [], [B]: [roleCell('extra', '2')] }),
    ]);
    const [cost] = roleCharts(half, entries(), []);
    expect(cost.groups.map((g) => g.name)).toEqual(['plan', 'extra']);
    expect(cost.groups[0].rows[0].marks[1]).toEqual({ value: null, word: '—' });
  });
});

describe('modelCharts', () => {
  const m = (v: string, key = 'm1'): ReturnType<typeof mcell> =>
    mcell({ scope_type: 'model', scope_key: key, model: key, value_num: v });

  it('pairs cost when a model gateway cell exists', () => {
    const p = payloadOf([
      metricOf('cost.gateway', { [A]: [m('1')], [B]: [] }),
      metricOf('cost.harness', { [A]: [m('2')], [B]: [m('3', 'm2')] }),
      metricOf('tokens.output', { [A]: [m('9')], [B]: [m('8', 'm2')] }),
    ]);
    const charts = modelCharts(p, entries());
    expect(charts.map((c) => c.title)).toEqual([
      'cost by model · gateway and harness',
      'output tokens by model',
    ]);
    expect(charts[0].kind).toBe('pair');
    expect(charts[0].groups.map((g) => g.name)).toEqual(['m1', 'm2']);
    expect(charts[0].groups[0].rows[1].marks[0]).toEqual({ value: null, word: '—' });
  });

  it('is harness only and says why when no gateway split is stored; blind gives two rows', () => {
    const p = payloadOf([
      metricOf('cost.harness', {
        [A]: [m('2', 'hidden · blind'), m('3', 'hidden · blind')],
        [B]: [],
      }),
    ]);
    const [cost] = modelCharts(p, entries());
    expect(cost.title).toBe('cost by model · harness');
    expect(cost.context).toContain(NO_MODEL_GATEWAY);
    expect(cost.groups).toHaveLength(1);
    expect(cost.groups[0].rows.map((r) => r.name)).toEqual([['R1'], ['R1'], ['R2']]);
    expect(new Set(cost.groups[0].rows.map((r) => r.id)).size).toBe(3);
  });

  it('skips charts without catalogue entries or models', () => {
    expect(modelCharts(payloadOf([run('tokens.output', ['1', '2'])]), entries())).toEqual([]);
    expect(modelCharts(payloadOf([]), entries([]))).toEqual([]);
  });
});

describe('familyCharts', () => {
  const fam = (
    family: string,
    differs: boolean,
    cells: Record<string, [string | null, string | null, string[]]>,
  ) => ({
    family,
    source: null,
    step_structure_differs: differs,
    cells: Object.fromEntries(
      Object.entries(cells).map(([k, [v, missing, roles]]) => [
        k,
        { value_num: v, missing, roles },
      ]),
    ),
  });

  it('groups by family, flags differing structure, outlines a partial and words a missing', () => {
    const out = metricOf(
      'tokens.output',
      {},
      {
        families: [
          fam('story work', true, {
            [A]: ['10', 'partial', ['plan', 'implement', 'review']],
            [B]: [null, 'not recorded', ['orchestrate']],
          }),
          fam('setup', false, { [A]: ['1', null, ['x']] }),
        ],
      },
    );
    const [chart] = familyCharts(payloadOf([out]), entries());
    expect(chart.title).toBe('output tokens by role · role family');
    expect(chart.groups.map((g) => g.name)).toEqual(['story work', 'setup']);
    expect(chart.flag).toBe(
      '≠ step structure differs · story work: R1 plan · implement · review; R2 orchestrate',
    );
    const [a, b] = chart.groups[0].rows;
    expect(a.marks[0].outline).toBe(true);
    expect(a.marks[0].value?.value_num).toBe('10');
    expect(a.marks[0].value?.missing).toBeNull();
    expect(b.marks[0]).toEqual({ value: null, word: 'not recorded' });
    expect(chart.groups[1].rows[1].marks[0]).toEqual({ value: null, word: '—' });
    expect(chart.groups[1].rows[0].marks[0].outline).toBeUndefined();
  });

  it('has no flag when no family differs and drops metrics without families', () => {
    const out = metricOf(
      'tokens.output',
      {},
      { families: [fam('f', false, { [A]: ['1', null, []] })] },
    );
    expect(familyCharts(payloadOf([out]), entries())[0].flag).toBeNull();
    expect(familyCharts(payloadOf([run('tokens.output', ['1', '2'])]), entries())).toEqual([]);
    const nullWord = metricOf(
      'tokens.output',
      {},
      { families: [fam('f', false, { [A]: [null, null, []] })] },
    );
    expect(familyCharts(payloadOf([nullWord]), entries())[0].groups[0].rows[0].marks[0].word).toBe(
      '—',
    );
  });

  it('projects a family cell to a value', () => {
    const v = familyValue(
      { value_num: null, missing: 'x', roles: [] },
      'tokens.output',
      'f',
      'tokens',
    );
    expect(v).toMatchObject({
      scope_type: 'role',
      scope_key: 'f',
      method_id: '',
      missing: 'x',
      origin: null,
    });
    expect(asValue(mcell(), 'a.b')).toMatchObject({ metric_id: 'a.b', origin: null });
  });
});

describe('chartsFor and rangeTicks', () => {
  const payload = payloadOf([run('tokens.output', ['1', '2'])]);
  const base = { set: 'headline', stepOrder: [] } as const;

  it('dispatches on breakdown and roles', () => {
    expect(
      chartsFor(payload, entries(), { ...base, breakdown: 'total', roles: 'declared' }),
    ).toHaveLength(1);
    expect(
      chartsFor(payload, entries(), { ...base, breakdown: 'role', roles: 'declared' }),
    ).toEqual([]);
    expect(chartsFor(payload, entries(), { ...base, breakdown: 'role', roles: 'family' })).toEqual(
      [],
    );
    expect(
      chartsFor(payload, entries(), { ...base, breakdown: 'model', roles: 'declared' }),
    ).toEqual([]);
  });

  it('starts a range above zero and widens a zero span', () => {
    const r = rangeTicks(1.5, 2.5);
    expect(r.origin).toBeGreaterThan(0);
    expect(r.ticks[0]).toBe(r.origin);
    expect(r.ticks.at(-1)!).toBeGreaterThanOrEqual(2.5);
    const flat = rangeTicks(2, 2);
    expect(flat.ticks[0]).toBeLessThan(2);
    expect(flat.ticks.at(-1)!).toBeGreaterThan(2);
    expect(rangeTicks(0, 0).origin).toBe(0);
  });
});
