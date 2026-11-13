/** `lib/run/metrics-glance.ts` (epic 3 story 3): every Run-page metric string, EXPERIENCE §4. */
import { describe, expect, it } from 'vitest';

import {
  calcLine,
  figuresDiffer,
  isEnded,
  nextVersion,
  recalcConfirmLine,
  retriesCount,
  runValue,
  targetFor,
  versionLine,
} from '../../src/lib/run/metrics-glance';
import { value, version } from './metrics-fixtures';

type Calc = Parameters<typeof calcLine>[0];

function calc(over: Partial<NonNullable<Calc>> = {}): NonNullable<Calc> {
  return {
    ended_at: null,
    entry_point: ['manual'],
    id: 'c1',
    output: '',
    queued_at: '2026-11-19T14:02:05Z',
    run_id: 'r',
    started_at: '2026-11-19T14:02:11Z',
    state: 'running',
    target_n: 4,
    ...over,
  };
}

describe('runValue', () => {
  const items = [
    value({ metric_id: 'cost.retries', source: 'gateway', value_num: '1' }),
    value({ metric_id: 'cost.retries', source: 'harness', value_num: '2' }),
    value({ metric_id: 'cost.retries', scope_type: 'attempt', value_num: '9' }),
  ];
  it('finds the Run-scope value, by source when given', () => {
    expect(runValue(items, 'cost.retries', 'harness')?.value_num).toBe('2');
    expect(runValue(items, 'cost.retries')?.value_num).toBe('1');
    expect(runValue(items, 'cost.retries', 'x')).toBeNull();
    expect(runValue(items, 'nope')).toBeNull();
  });
});

describe('isEnded', () => {
  it('is true for done, failed and cancelled only', () => {
    expect(['done', 'failed', 'cancelled'].every(isEnded)).toBe(true);
    expect(['queued', 'running', 'needs_you'].some(isEnded)).toBe(false);
  });
});

describe('figuresDiffer', () => {
  const g = (n: string | null) => value({ metric_id: 'cost.gateway', value_num: n });
  const h = (n: string | null) => value({ metric_id: 'cost.harness', value_num: n });

  it('names the higher figure and the gap', () => {
    expect(figuresDiffer(g('15.35'), h('16.01'))).toEqual({
      line: 'gateway $15.35 · harness $16.01 · harness is $0.66 higher (4.3 %)',
      gate: 'the budget gate uses the higher figure',
    });
  });
  it('reads gateway is higher when it is', () => {
    expect(figuresDiffer(g('16.01'), h('15.35'))?.line).toBe(
      'gateway $16.01 · harness $15.35 · gateway is $0.66 higher (4.3 %)',
    );
  });
  it('is null when equal at cents or when either is missing', () => {
    expect(figuresDiffer(g('15.35'), h('15.35'))).toBeNull();
    expect(figuresDiffer(g('15.351'), h('15.349'))).toBeNull();
    expect(figuresDiffer(g(null), h('1'))).toBeNull();
    expect(figuresDiffer(h('1'), null)).toBeNull();
    expect(figuresDiffer(null, null)).toBeNull();
  });
  it('omits the percentage when the lower figure is 0', () => {
    expect(figuresDiffer(g('0'), h('2'))?.line).toBe(
      'gateway $0.00 · harness $2.00 · harness is $2.00 higher',
    );
  });
});

describe('retriesCount', () => {
  const r = (n: string | null, missing: string | null = null) =>
    value({ metric_id: 'process.retries', value_num: n, missing });
  it('sums the Run-scope counts', () => {
    expect(retriesCount([r('2'), r('3')])).toBe('5');
  });
  it('prints the missing word, never 0, and null when none exist', () => {
    expect(retriesCount([r('2'), r(null, 'not recorded')])).toBe('not recorded');
    expect(retriesCount([r(null, null)])).toBe('');
    expect(retriesCount([])).toBeNull();
  });
});

describe('versions', () => {
  const three = [version(1), version(3), version(2)];
  it('versionLine shows only for an older selection', () => {
    expect(versionLine(three, 1)).toBe('showing v1 of 3 · latest is v3');
    expect(versionLine(three, 3)).toBeNull();
    expect(versionLine([], 1)).toBeNull();
  });
  it('nextVersion is max + 1', () => {
    expect(nextVersion(three)).toBe(4);
    expect(nextVersion([])).toBe(1);
  });
  it('recalcConfirmLine counts the kept versions', () => {
    expect(recalcConfirmLine(three)).toBe(
      "Creates v4 of this Run's metrics: part A from the Run record. v1 to v3 are kept.",
    );
    expect(recalcConfirmLine([version(1)])).toBe(
      "Creates v2 of this Run's metrics: part A from the Run record. v1 is kept.",
    );
    expect(recalcConfirmLine([])).toBe(
      "Creates v1 of this Run's metrics: part A from the Run record.",
    );
  });
});

describe('calcLine', () => {
  it('reads the running, queued and failed lines', () => {
    expect(calcLine(calc())).toBe('calculating v4 · started 14:02:11');
    expect(calcLine(calc({ state: 'queued', started_at: null }))).toBe(
      'calculating v4 · started 14:02:05',
    );
    expect(calcLine(calc({ state: 'failed' }))).toBe(
      'calculation v4 failed · no version created ·',
    );
  });
  it('is null when done or absent', () => {
    expect(calcLine(calc({ state: 'done' }))).toBeNull();
    expect(calcLine(null)).toBeNull();
  });
});

describe('targetFor', () => {
  it('builds the origin target from the context', () => {
    const v = value();
    const ver = version(2);
    const t = targetFor(v, {
      runLabel: 'L',
      versions: [version(1), ver],
      selected: 2,
      latest: 2,
      projectName: 'p',
      items: [v],
      subscription: false,
    });
    expect(t).toMatchObject({ runLabel: 'L', version: ver, latest: 2, projectName: 'p' });
    expect(t.spans).toEqual({ models: 0, repositories: 0 });
  });
  it('has no version when none matches', () => {
    const t = targetFor(value(), {
      runLabel: 'L',
      versions: [],
      selected: null,
      latest: null,
      projectName: 'p',
      items: [],
      subscription: true,
    });
    expect(t.version).toBeNull();
    expect(t.subscription).toBe(true);
  });
});
