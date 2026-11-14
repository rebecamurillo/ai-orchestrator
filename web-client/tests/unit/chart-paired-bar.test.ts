// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import PairedBarChart from '../../src/components/charts/PairedBarChart';
import { NO_MODEL_GATEWAY, type PairRow } from '../../src/lib/charts/run-charts';
import type { TargetContext } from '../../src/lib/run/metrics-glance';
import { $originTarget, closeOrigin } from '../../src/stores/metric-ui';
import { value } from './metrics-fixtures';

const ctx: TargetContext = {
  runLabel: 'Run 7',
  versions: [],
  selected: null,
  latest: 1,
  items: [],
  subscription: false,
};
const gw = (over = {}) => value({ metric_id: 'cost.gateway', scope_type: 'role', ...over });
const hn = (over = {}) => value({ metric_id: 'cost.harness', scope_type: 'role', ...over });

function draw(rows: PairRow[]) {
  return render(
    createElement(PairedBarChart, {
      title: 'cost by role',
      keyText: 'gateway · harness',
      rows,
      unit: 'USD',
      ctx,
      labels: { gateway: 'Gateway cost', harness: 'Harness cost' },
    }),
  );
}

afterEach(() => {
  cleanup();
  closeOrigin();
});

describe('PairedBarChart', () => {
  const rows: PairRow[] = [
    {
      id: 'r1',
      label: 'implement',
      gateway: gw({ value_num: '10' }),
      harness: hn({ value_num: '16.01', partial_n: 11, partial_m: 12 }),
    },
    {
      id: 'r2',
      label: 'senior',
      gateway: gw({ value_num: '5', carried_from: 1 }),
      harness: hn({ value_num: '4' }),
    },
  ];

  it('draws a partial total as an outline with its label and a carried value solid', () => {
    const { container } = draw(rows);
    const partial = screen.getByRole('button', {
      name: 'Run 7 implement Harness cost $16.01 partial · 11 of 12 attempts',
    });
    const rect = partial.querySelector('rect');
    expect(rect?.getAttribute('fill')).toBe('none');
    expect(rect?.getAttribute('stroke')).toBe('var(--color-chart-data-2)');
    expect(partial.querySelector('text')?.textContent).toBe('$16.01 · partial · 11 of 12 attempts');
    const carried = screen.getByRole('button', { name: /senior Gateway cost/ });
    expect(carried.querySelector('rect')?.getAttribute('fill')).toBe('var(--color-chart-data-1)');
    expect(carried.querySelector('text')?.textContent).toBe('$5.00 from v1');
    expect(container.querySelectorAll('[role="button"]')).toHaveLength(4);
  });

  it('draws 8 px bars 2 px apart, gateway in data-1 above harness in data-2', () => {
    draw(rows);
    const [g, h] = screen
      .getAllByRole('button')
      .slice(0, 2)
      .map((b) => b.querySelector('rect')!);
    expect(g.getAttribute('height')).toBe('8');
    expect(h.getAttribute('height')).toBe('8');
    expect(Number(h.getAttribute('y')) - Number(g.getAttribute('y'))).toBe(10);
    expect(g.getAttribute('fill')).toBe('var(--color-chart-data-1)');
    expect(h.getAttribute('stroke')).toBe('var(--color-chart-data-2)');
  });

  it('lists marks in Run order, gateway before harness, each named by its parts', () => {
    draw(rows);
    const names = screen.getAllByRole('button').map((b) => b.getAttribute('aria-label'));
    expect(names).toEqual([
      'Run 7 implement Gateway cost $10.00',
      'Run 7 implement Harness cost $16.01 partial · 11 of 12 attempts',
      'Run 7 senior Gateway cost $5.00 from v1',
      'Run 7 senior Harness cost $4.00',
    ]);
    for (const b of screen.getAllByRole('button')) expect(b.getAttribute('tabindex')).toBe('0');
  });

  it('shows the tooltip with only the name parts, on focus and on hover', () => {
    draw(rows);
    const [first, second] = screen.getAllByRole('button');
    fireEvent.focus(first);
    expect(screen.getByRole('tooltip').textContent).toBe(
      'Run 7 · implement · Gateway cost · $10.00',
    );
    fireEvent.blur(first);
    expect(screen.queryByRole('tooltip')).toBeNull();
    fireEvent.mouseEnter(second);
    expect(screen.getByRole('tooltip').textContent).toBe(
      'Run 7 · implement · Harness cost · $16.01 · partial · 11 of 12 attempts',
    );
    fireEvent.mouseLeave(second);
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('opens the origin drawer for the value on Enter', () => {
    draw(rows);
    fireEvent.keyDown(screen.getAllByRole('button')[1], { key: 'Enter' });
    expect($originTarget.get()?.value.value_num).toBe('16.01');
    expect($originTarget.get()?.runLabel).toBe('Run 7');
  });

  it('puts a gateway word in the gateway slot and draws only the harness mark', () => {
    const { container } = draw([
      {
        id: 'm',
        label: 'sonnet',
        gateway: null,
        gatewayWord: NO_MODEL_GATEWAY,
        harness: hn({ value_num: '3' }),
      },
      {
        id: 'n',
        label: 'shell',
        gateway: gw({ value_num: null, missing: 'n/a — shell step' }),
        harness: null,
      },
    ]);
    expect(screen.getByText(NO_MODEL_GATEWAY)).toBeTruthy();
    expect(screen.getByText('n/a — shell step')).toBeTruthy();
    expect(container.querySelectorAll('[role="button"]')).toHaveLength(1);
  });

  it('draws a hatched share over the end of its own bar', () => {
    const { container } = draw([
      {
        id: 's',
        label: 'story',
        gateway: gw({ value_num: '10' }),
        harness: hn({ value_num: '10' }),
        gatewayShare: gw({ value_num: '4', metric_id: 'cost.retries', source: 'gateway' }),
        harnessShare: gw({ value_num: null, missing: 'not recorded' }),
      },
    ]);
    const rects = screen.getAllByRole('button')[0].querySelectorAll('rect');
    expect(rects).toHaveLength(2);
    expect(rects[1].getAttribute('fill')).toBe('url(#hatch-1)');
    expect(
      Number(rects[0].getAttribute('width')) + Number(rects[1].getAttribute('width')),
    ).toBeCloseTo(
      Number(screen.getAllByRole('button')[1].querySelector('rect')?.getAttribute('width')),
    );
    expect(container.querySelectorAll('pattern')).toHaveLength(3);
  });
});
