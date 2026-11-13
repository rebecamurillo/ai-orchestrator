// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import CompareBar from '../../src/components/metrics/CompareBar';
import type { CompareState } from '../../src/lib/metrics/compare';
import { A, B, PROJECT } from './metrics-compare-fixtures';

afterEach(cleanup);

const state: CompareState = {
  runIds: [A, B],
  versions: {},
  view: 'table',
  set: 'headline',
  blind: false,
};
const onChange = vi.fn();
const onExport = vi.fn();
const mount = (over: Partial<CompareState> = {}, exportLine = '') =>
  render(
    createElement(CompareBar, {
      state: { ...state, ...over },
      projectId: PROJECT,
      onChange,
      onExport,
      exportLine,
    }),
  );

describe('CompareBar', () => {
  it('shows both segments, TABLE pressed, CHART enabled (story 4.4, 2026-11-13: the chart view exists)', () => {
    mount();
    expect(screen.getByTestId('compare-view-table').getAttribute('aria-pressed')).toBe('true');
    const chart = screen.getByTestId('compare-view-chart') as HTMLButtonElement;
    expect(chart.disabled).toBe(false);
    expect(chart.hasAttribute('aria-disabled')).toBe(false);
    expect(chart.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(chart);
    expect(onChange).toHaveBeenCalledWith({ ...state, view: 'chart' });
    cleanup();
    mount({ view: 'chart' });
    expect(screen.getByTestId('compare-view-chart').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('compare-view-table').getAttribute('aria-pressed')).toBe('false');
  });

  it('switches the metric set through onChange', () => {
    mount();
    expect(screen.getByTestId('compare-set-headline').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByTestId('compare-set-all'));
    expect(onChange).toHaveBeenCalledWith({ ...state, set: 'all' });
    fireEvent.click(screen.getByTestId('compare-set-headline'));
    expect(onChange).toHaveBeenLastCalledWith({ ...state, set: 'headline' });
  });

  it('has blind as a switch', () => {
    mount({ blind: true });
    const sw = screen.getByTestId('compare-blind');
    expect(sw.getAttribute('role')).toBe('switch');
    expect(sw.getAttribute('aria-checked')).toBe('true');
    fireEvent.click(sw);
    expect(onChange).toHaveBeenLastCalledWith({ ...state, blind: false });
  });

  it('links add runs to Metrics with the selection', () => {
    mount();
    expect(screen.getByTestId('compare-add-runs').getAttribute('href')).toBe(
      `/metrics?project=${PROJECT}&select=${A},${B}`,
    );
  });

  it('exports on click and prints the line as a status', () => {
    mount({}, 'exported x');
    fireEvent.click(screen.getByTestId('compare-export'));
    expect(onExport).toHaveBeenCalled();
    const line = screen.getByTestId('compare-export-line');
    expect(line.textContent).toBe('exported x');
    expect(line.getAttribute('role')).toBe('status');
    expect(screen.getByTestId('compare-export').textContent).toBe('EXPORT CSV + JSON');
  });
});
