// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import ChartMark from '../../src/components/charts/ChartMark';
import { markFor } from '../../src/lib/charts/layout';
import type { TargetContext } from '../../src/lib/run/metrics-glance';
import { value } from './metrics-fixtures';

const ctx: TargetContext = {
  runLabel: 'Run 7',
  versions: [],
  selected: null,
  latest: 1,
  items: [],
  subscription: false,
};
const v = value({ value_num: '5' });

function mount(extra: { outlined?: boolean; dotted?: boolean } = {}) {
  return render(
    createElement(
      'svg',
      null,
      createElement(ChartMark, {
        x: 10,
        y: 20,
        height: 12,
        mark: markFor(v, 10, 100),
        series: 1,
        value: v,
        ctx,
        rowLabel: 'r',
        seriesLabel: null,
        onTip: () => undefined,
        ...extra,
      }),
    ),
  ).container;
}

afterEach(cleanup);

describe('ChartMark follow and dots', () => {
  it('renders as before with neither prop', () => {
    const c = mount();
    expect(c.querySelector('[data-follow]')).toBeNull();
    expect(c.querySelector('rect')?.getAttribute('fill')).toBe('var(--color-chart-data-1)');
  });

  it('outlines the mark extent in the accent colour once', () => {
    const c = mount({ outlined: true });
    const found = c.querySelectorAll('[data-follow]');
    expect(found).toHaveLength(1);
    const rect = found[0];
    expect(rect.getAttribute('stroke')).toBe('var(--color-accent)');
    expect(rect.getAttribute('fill')).toBe('none');
    expect(rect.getAttribute('x')).toBe('9');
    expect(rect.getAttribute('y')).toBe('19');
    expect(rect.getAttribute('width')).toBe('52');
    expect(rect.getAttribute('height')).toBe('14');
  });

  it('fills a dotted mark with the dot pattern and a series stroke', () => {
    const rect = mount({ dotted: true }).querySelector('rect');
    expect(rect?.getAttribute('fill')).toBe('url(#dots-1)');
    expect(rect?.getAttribute('stroke')).toBe('var(--color-chart-data-1)');
  });
});
