// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { components } from '../../src/api/schema';
import MetricsRunsTable from '../../src/components/metrics/MetricsRunsTable';
import { runRowView } from '../../src/lib/metrics/home';

type Run = components['schemas']['MetricsRunOut'];

const run = (id: string, over: Partial<Run> = {}): Run => ({
  base_branch: 'main',
  branch: 'feat/x',
  gateway: '1.5',
  harness: 'claude',
  harness_spend: '2',
  id,
  label: `label ${id}`,
  label_set_by_operator: false,
  latest_version: 2,
  selectable: true,
  status: 'done',
  subscription: null,
  template_name: 'story',
  template_version: 3,
  wall_clock_seconds: 60,
  ...over,
});

const A = 'aaaaaaaa-0000-7000-8000-000000000001';
const B = 'bbbbbbbb-0000-7000-8000-000000000002';
const R = 'cccccccc-0000-7000-8000-000000000003';

function mount(selected: string[], onToggle = vi.fn(), onClear = vi.fn()) {
  const rows = [
    run(R, { status: 'running', selectable: false, latest_version: null }),
    run(A, { label_set_by_operator: true }),
    run(B, { status: 'cancelled', latest_version: null }),
  ].map(runRowView);
  render(createElement(MetricsRunsTable, { rows, selected, onToggle, onClear }));
  return { onToggle, onClear };
}

afterEach(cleanup);

describe('MetricsRunsTable', () => {
  it('renders boxes on ended rows only, and the running word', () => {
    mount([]);
    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
    const row = screen.getByTestId(`metrics-run-row-${R}`);
    expect(within(row).getByText('running')).toBeTruthy();
    expect(within(row).getByText('values so far')).toBeTruthy();
    expect(within(screen.getByTestId(`metrics-run-row-${A}`)).getByText('v2')).toBeTruthy();
    expect(
      within(screen.getByTestId(`metrics-run-row-${B}`)).getByText('no result version'),
    ).toBeTruthy();
    expect(within(screen.getByTestId(`metrics-run-row-${A}`)).getByText('your label')).toBeTruthy();
    expect(within(row).getByText('cccccccc').getAttribute('href')).toBe(`/workflows/${R}`);
  });

  it('toggles through the checkbox and reports checked state', () => {
    const { onToggle } = mount([A]);
    expect(screen.getByTestId(`metrics-run-select-${A}`).getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId(`metrics-run-select-${B}`).getAttribute('aria-checked')).toBe(
      'false',
    );
    fireEvent.click(screen.getByTestId(`metrics-run-select-${B}`));
    expect(onToggle).toHaveBeenCalledWith(B);
  });

  it('disables COMPARE below two and links from two', () => {
    mount([A]);
    const c = screen.getByTestId('metrics-compare');
    expect(c.tagName).toBe('BUTTON');
    expect((c as HTMLButtonElement).disabled).toBe(true);
    expect(c.textContent).toBe('COMPARE 1 RUNS');
    expect(screen.getByTestId('metrics-selection-count').textContent).toBe('1 selected');
    cleanup();
    mount([A, B]);
    const l = screen.getByTestId('metrics-compare');
    expect(l.tagName).toBe('A');
    expect(l.getAttribute('href')).toBe(`/metrics/compare?runs=${A},${B}`);
    expect(l.textContent).toBe('COMPARE 2 RUNS');
  });

  it('clears', () => {
    const { onClear } = mount([A, B]);
    fireEvent.click(screen.getByTestId('metrics-clear'));
    expect(onClear).toHaveBeenCalled();
  });
});
