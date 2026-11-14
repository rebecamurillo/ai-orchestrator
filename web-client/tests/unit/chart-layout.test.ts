import { describe, expect, it } from 'vitest';

import {
  BAR,
  CHART_WIDTH,
  GUTTER,
  VALUE_SPACE,
  ZERO_TICK,
  decimals,
  layoutRows,
  markFor,
  niceTicks,
  rowHeight,
  scale,
  secondsTicks,
  textureFor,
  tickLabel,
  wrapLabel,
} from '../../src/lib/charts/layout';
import { value } from './metrics-fixtures';

const PLOT = CHART_WIDTH - GUTTER - VALUE_SPACE;

describe('niceTicks', () => {
  it('prints 0, 0.25, 0.5, 0.75 for the max of 0.1, 0.2, 0.7', () => {
    const { step, ticks } = niceTicks(0.7);
    expect(ticks.map((t) => tickLabel(t, step, 'ratio'))).toEqual(['0', '0.25', '0.5', '0.75']);
  });

  it.each([1, 7, 12, 0.03, 16.01, 7394724])('is nice and covers %s', (max) => {
    const { step, ticks } = niceTicks(max);
    const mantissa = step / 10 ** Math.floor(Math.log10(step) + 1e-9);
    expect([1, 2, 2.5, 5].some((m) => Math.abs(m - mantissa) < 1e-9)).toBe(true);
    expect(ticks.length).toBeGreaterThanOrEqual(3);
    expect(ticks.length).toBeLessThanOrEqual(4);
    expect(ticks[0]).toBe(0);
    expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(max);
    for (const t of ticks) {
      expect(tickLabel(t, step, 'ratio')).not.toMatch(/\.\d*(0{5,}|9{5,})/);
    }
  });

  it('gives 0 and 1 for a max of 0', () => {
    expect(niceTicks(0)).toEqual({ step: 1, ticks: [0, 1] });
    expect(niceTicks(-3)).toEqual({ step: 1, ticks: [0, 1] });
  });
});

describe('decimals and tickLabel', () => {
  it('counts the digits after the point', () => {
    expect(decimals(5)).toBe(0);
    expect(decimals(2.5)).toBe(1);
    expect(decimals(0.25)).toBe(2);
  });

  it('prints each unit', () => {
    expect(tickLabel(0, 2.5, 'USD')).toBe('$0');
    expect(tickLabel(2.5, 2.5, 'USD')).toBe('$2.5');
    expect(tickLabel(7500000, 2500000, 'tokens')).toBe('7,500,000');
    expect(tickLabel(1800, 1800, 'seconds')).toBe('0h 30m');
  });

  it('computes second ticks on minutes', () => {
    const { step, ticks } = secondsTicks(3600);
    expect(step).toBe(1200);
    expect(ticks).toEqual([0, 1200, 2400, 3600]);
    expect(secondsTicks(0).ticks).toEqual([0, 60]);
  });

  it('keeps second ticks on whole minutes so no two labels read the same', () => {
    for (const max of [20, 60, 170, 400, 450]) {
      const { step, ticks } = secondsTicks(max);
      expect(step % 60).toBe(0);
      expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(max);
      const labels = ticks.map((t) => tickLabel(t, step, 'seconds'));
      expect(new Set(labels).size).toBe(labels.length);
    }
    expect(secondsTicks(20).ticks).toEqual([0, 60]);
    expect(secondsTicks(450).ticks).toEqual([0, 300, 600]);
  });
});

describe('scale', () => {
  it('is linear from zero', () => {
    expect(scale(0, 10)).toBe(0);
    expect(scale(10, 10)).toBe(PLOT);
    expect(scale(5, 10)).toBe(PLOT / 2);
    expect(scale(5, 0)).toBe(0);
  });
});

describe('wrapLabel', () => {
  it('keeps a short label on one line', () => {
    expect(wrapLabel('epic 1 · story 1-1')).toEqual(['epic 1 · story 1-1']);
  });

  it('breaks at the last separator before the limit', () => {
    expect(wrapLabel('epic 1 · story 1-1 · a longer tail', undefined, 22)).toEqual([
      'epic 1 · story 1-1',
      'a longer tail',
    ]);
    expect(wrapLabel('alpha beta gamma delta epsilon', undefined, 18)).toEqual([
      'alpha beta gamma',
      'delta epsilon',
    ]);
  });

  it('cuts at the limit without a separator and ends the second line with an ellipsis', () => {
    expect(wrapLabel('x'.repeat(30), undefined, 10)).toEqual(['x'.repeat(10), 'xxxxxxxxx…']);
  });

  it('adds the short id as a line', () => {
    expect(wrapLabel('short', '0190ab')).toEqual(['short', '0190ab']);
  });
});

describe('markFor', () => {
  it('has no width for a missing value and carries its word', () => {
    const m = markFor(value({ value_num: null, missing: 'not recorded' }), 10);
    expect(m).toMatchObject({ kind: 'missing', word: 'not recorded', width: 0 });
    expect(markFor(value({ value_num: null, missing: null }), 10).word).toBe('');
  });

  it('draws a zero as a 2 px tick labelled 0', () => {
    expect(markFor(value({ value_num: '0' }), 10)).toMatchObject({
      kind: 'zero',
      width: ZERO_TICK,
      label: '0',
    });
  });

  it('labels a partial total and never fills it', () => {
    const m = markFor(value({ value_num: '16.01', partial_n: 11, partial_m: 12 }), 20);
    expect(m.kind).toBe('partial');
    expect(m.label).toBe('$16.01 · partial · 11 of 12 attempts');
  });

  it('labels a carried value', () => {
    const m = markFor(value({ value_num: '5', carried_from: 1 }), 10);
    expect(m).toMatchObject({ kind: 'bar', label: '$5.00 from v1', width: PLOT / 2 });
  });

  it('labels a plain value', () => {
    expect(markFor(value({ value_num: '10' }), 10)).toMatchObject({
      kind: 'bar',
      label: '$10.00',
    });
  });
});

describe('textureFor, rowHeight, layoutRows', () => {
  it('uses dots only for another method and hatch only for a share', () => {
    expect(textureFor({ share: false, otherMethod: true })).toBe('dots');
    expect(textureFor({ share: true, otherMethod: false })).toBe('hatch');
    expect(textureFor({ share: false, otherMethod: false })).toBe('solid');
  });

  it('sizes rows by kind and label lines', () => {
    expect(rowHeight('single', 1)).toBeGreaterThanOrEqual(BAR);
    expect(rowHeight('pair', 1)).toBeGreaterThan(rowHeight('single', 1));
    expect(rowHeight('single', 3)).toBeGreaterThan(rowHeight('single', 1));
  });

  it('stacks rows', () => {
    expect(layoutRows([10, 20])).toEqual({ tops: [0, 10], total: 30 });
  });
});
