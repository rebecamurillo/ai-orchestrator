// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import ChartFrame from '../../src/components/charts/ChartFrame';
import { markParts, valueText } from '../../src/components/charts/ChartMark';
import { niceTicks } from '../../src/lib/charts/layout';
import type { TargetContext } from '../../src/lib/run/metrics-glance';
import { value } from './metrics-fixtures';

const ctx: TargetContext = {
  runLabel: 'Run 7',
  versions: [],
  selected: null,
  latest: 1,
  items: [],
  subscription: true,
};

afterEach(cleanup);

describe('ChartMark text', () => {
  it('prints a figure or the missing word as the table cell does', () => {
    expect(valueText(value({ value_num: '1.5' }))).toBe('$1.50');
    expect(valueText(value({ value_num: null, missing: 'not recorded' }))).toBe('not recorded');
    expect(valueText(value({ value_num: null, missing: null }))).toBe('');
  });

  it('builds the name parts with state words and an optional series', () => {
    const v = value({ value_num: '2', carried_from: 1 });
    expect(markParts(v, ctx, 'implement', 'Gateway cost')).toEqual([
      'Run 7',
      'implement',
      'Gateway cost',
      '$2.00',
      'list-price equivalent',
      'from v1',
    ]);
    expect(markParts(v, ctx, 'implement', null).slice(0, 3)).toEqual([
      'Run 7',
      'implement',
      '$2.00',
    ]);
  });
});

describe('ChartFrame', () => {
  it('is a labelled figure with a head, wrapped row labels and the tooltip only when set', () => {
    const props = {
      title: 'cost by role',
      keyText: 'key',
      ticks: niceTicks(7),
      unit: 'USD',
      height: 40,
      rows: [{ id: 'a', label: 'epic 1 · story 1-1 · a very long label here', top: 0, height: 40 }],
    };
    const { rerender, container } = render(
      createElement(ChartFrame, { ...props, tip: null, children: createElement('g') }),
    );
    expect(screen.getByRole('figure').getAttribute('aria-label')).toBe('cost by role');
    expect(container.querySelectorAll('tspan')).toHaveLength(2);
    expect(container.textContent).toContain('$7.5');
    expect(screen.queryByRole('tooltip')).toBeNull();
    rerender(createElement(ChartFrame, { ...props, tip: 'hello', children: createElement('g') }));
    expect(screen.getByRole('tooltip').textContent).toBe('hello');
  });
});
