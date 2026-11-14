// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import BarChart from '../../src/components/charts/BarChart';
import type { ChartRow } from '../../src/lib/charts/run-charts';
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
const tokens = (over = {}) =>
  value({ metric_id: 'tokens.output', unit: 'tokens', scope_type: 'role', ...over });

function draw(rows: ChartRow[], extra: Record<string, unknown> = {}) {
  return render(
    createElement(BarChart, {
      title: 'tokens by role · output',
      keyText: 'output',
      rows,
      unit: 'tokens',
      ctx,
      seriesLabel: 'output',
      ...extra,
    }),
  );
}

afterEach(() => {
  cleanup();
  closeOrigin();
});

describe('BarChart', () => {
  const rows: ChartRow[] = [
    { id: 'a', label: 'implement', value: tokens({ value_num: '1200' }) },
    { id: 'b', label: 'senior', value: tokens({ value_num: null, missing: 'not recorded' }) },
    { id: 'c', label: 'review', value: tokens({ value_num: '0' }) },
    { id: 'd', label: 'unused', value: null },
  ];

  it('gives a missing value its word and no mark, keeping the row', () => {
    const { container } = draw(rows);
    expect(screen.getByText('not recorded')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /senior/ })).toBeNull();
    expect(container.querySelectorAll('[role="button"]')).toHaveLength(2);
    expect(container.querySelectorAll('rect')).toHaveLength(2);
    expect(container.textContent).not.toMatch(/—|\$0\.00/);
  });

  it('draws a real zero as a 2 px focusable tick labelled 0', () => {
    const { container } = draw(rows);
    const button = screen.getByRole('button', { name: 'Run 7 review output 0' });
    expect(button.getAttribute('tabindex')).toBe('0');
    expect(button.querySelector('rect')?.getAttribute('width')).toBe('2');
    expect(button.querySelector('text')?.textContent).toBe('0');
    expect(container.querySelectorAll('text').length).toBeGreaterThan(3);
  });

  it('is a figure whose text, axis and gridlines use the chart ink at 12 px', () => {
    const { container } = draw(rows);
    const figure = screen.getByRole('figure');
    expect(figure.getAttribute('aria-label')).toBe('tokens by role · output');
    for (const text of container.querySelectorAll('text')) {
      expect(text.getAttribute('fill')).toBe('var(--color-chart-ink)');
    }
    const lines = container.querySelectorAll('svg > g > line');
    expect(lines.length).toBeGreaterThanOrEqual(3);
    for (const line of lines) {
      expect(line.getAttribute('stroke')).toBe('var(--color-chart-ink)');
      expect(line.getAttribute('stroke-opacity')).toBe('0.35');
    }
    expect(container.querySelector('svg')?.getAttribute('font-size')).toBe('12');
    expect(container.querySelector('rect')?.getAttribute('fill')).toBe('var(--color-chart-data-1)');
  });

  it('shows the tooltip on focus and mouse enter and opens the origin on Enter, Space and click', () => {
    draw(rows);
    const button = screen.getByRole('button', { name: /implement/ });
    expect(screen.queryByRole('tooltip')).toBeNull();
    fireEvent.focus(button);
    expect(screen.getByRole('tooltip').textContent).toBe('Run 7 · implement · output · 1,200');
    fireEvent.blur(button);
    expect(screen.queryByRole('tooltip')).toBeNull();
    fireEvent.mouseEnter(button);
    expect(screen.getByRole('tooltip').textContent).toBe('Run 7 · implement · output · 1,200');
    fireEvent.mouseLeave(button);
    expect(screen.queryByRole('tooltip')).toBeNull();

    fireEvent.keyDown(button, { key: 'a' });
    expect($originTarget.get()).toBeNull();
    fireEvent.keyDown(button, { key: 'Enter' });
    expect($originTarget.get()?.value.value_num).toBe('1200');
    closeOrigin();
    fireEvent.keyDown(button, { key: ' ' });
    expect($originTarget.get()?.value.value_num).toBe('1200');
    closeOrigin();
    fireEvent.click(button);
    expect($originTarget.get()?.value.value_num).toBe('1200');
  });

  it('draws a hatched row in data-2 with a 1 px outline on a duration axis', () => {
    const { container } = draw(
      [
        {
          id: 'p',
          label: 'waiting',
          texture: 'hatch',
          value: tokens({ value_num: '3600', unit: 'seconds' }),
        },
      ],
      { unit: 'seconds', ticksIn: 'seconds', seriesLabel: null },
    );
    const rect = container.querySelector('[role="button"] rect');
    expect(rect?.getAttribute('fill')).toBe('url(#hatch-2)');
    expect(rect?.getAttribute('stroke')).toBe('var(--color-chart-data-2)');
    expect(rect?.getAttribute('stroke-width')).toBe('1');
    expect(container.textContent).toContain('1h 00m');
    expect(screen.getByRole('button').getAttribute('aria-label')).toBe('Run 7 waiting 1h 00m');
  });
});
