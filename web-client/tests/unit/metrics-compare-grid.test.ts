// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CompareHeader from '../../src/components/metrics/CompareHeader';
import CompareGrid from '../../src/components/metrics/CompareGrid';
import { $catalogue } from '../../src/stores/catalogue';
import { $originTarget } from '../../src/stores/metric-ui';
import { entry } from './metrics-fixtures';
import { A, B, C, cell, comparePayload, header, metric } from './metrics-compare-fixtures';

const onRemove = vi.fn();
const onVersion = vi.fn();

beforeEach(() => {
  $catalogue.set({
    status: 'ready',
    entries: {
      'cost.gateway': entry('cost.gateway', { group: 'cost', level: 'H' }),
      'cost.harness': entry('cost.harness', { group: 'cost', level: 'H' }),
      'tokens.input': entry('tokens.input', { group: 'tokens', level: 'A', unit: 'tokens' }),
      'time.wall': entry('time.wall', { group: 'time', level: 'H', unit: 'seconds' }),
    },
  });
});
afterEach(() => {
  cleanup();
  $originTarget.set(null);
  onRemove.mockReset();
  onVersion.mockReset();
});

const mount = (payload = comparePayload(), set: 'headline' | 'all' = 'all') =>
  render(createElement(CompareGrid, { payload, set, onRemove, onVersion }));

describe('CompareGrid header', () => {
  it('renders one column per Run in order with every header field', () => {
    const payload = comparePayload([A, B, C]);
    payload.runs[1] = header(B, { label_set_by_operator: true, stories_done: null });
    mount(payload);
    const cols = [A, B, C].map((id) => screen.getByTestId(`compare-col-${id}`));
    expect(
      cols[0].compareDocumentPosition(cols[1]) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    const first = within(cols[0]);
    expect(first.getByText('DON')).toBeTruthy();
    expect(first.getByText(A.slice(0, 8)).getAttribute('href')).toBe(`/workflows/${A}`);
    expect(first.getByText('story@3')).toBeTruthy();
    expect(first.getByText('claude')).toBeTruthy();
    expect(first.getByText('coder: m1 · m2')).toBeTruthy();
    expect(first.getByText('base main')).toBeTruthy();
    expect(first.getByText('3/4 stories')).toBeTruthy();
    expect(first.queryByText('your label')).toBeNull();
    expect(within(cols[1]).getByText('your label')).toBeTruthy();
    expect(within(cols[1]).queryByText(/stories/)).toBeNull();
  });

  it('shows a version segment per version, the selected one pressed, the highest latest', () => {
    mount();
    expect(screen.getByTestId(`compare-version-${A}-1`).textContent).toBe('v1');
    expect(screen.getByTestId(`compare-version-${A}-2`).textContent).toBe('v2 latest');
    expect(screen.getByTestId(`compare-version-${A}-2`).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId(`compare-version-${A}-1`).getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(screen.getByTestId(`compare-version-${A}-1`));
    expect(onVersion).toHaveBeenCalledWith(A, 1, 2);
  });

  it('removes a Run, and refuses at two', () => {
    mount();
    fireEvent.click(screen.getByTestId(`compare-remove-${B}`));
    expect(onRemove).toHaveBeenCalledWith(B);
    cleanup();
    mount(comparePayload([A, B]));
    expect((screen.getByTestId(`compare-remove-${A}`) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId(`compare-remove-${B}`) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('CompareGrid body', () => {
  it('shows the same-work row with its flag only when the work differs', () => {
    const payload = comparePayload([A, B]);
    payload.same_work.differs = true;
    mount(payload);
    const row = screen.getByTestId('compare-same-work');
    expect(row.textContent).toContain('same work?');
    expect(row.textContent).toContain('≠ the work differs');
    expect(row.textContent).toContain('acme/app:abcdef01');
    expect(row.textContent).toContain('init');
    cleanup();
    mount(comparePayload([A, B]));
    expect(screen.getByTestId('compare-same-work').textContent).not.toContain('≠');
  });

  it('orders the group heads and drops empty ones; headline keeps level H', () => {
    mount();
    const heads = [...document.querySelectorAll('tr.compare-grp')].map((r) => r.textContent);
    expect(heads).toEqual(['COST', 'TOKENS', 'TIME', 'STATIC SIGNALS ON THE CHANGE']);
    cleanup();
    mount(comparePayload(), 'headline');
    expect(screen.queryByTestId('compare-group-tokens')).toBeNull();
    expect(screen.getByTestId('compare-group-cost')).toBeTruthy();
  });

  it('flags a metric whose methods differ, with each run method under the value', () => {
    const payload = comparePayload([A, B]);
    payload.metrics = [
      metric('cost.gateway', [A, B], {
        methods_differ: true,
        methods: { [A]: ['cost.gateway@1'], [B]: ['cost.gateway@2'] },
      }),
      metric('time.wall', [A, B]),
    ];
    mount(payload);
    expect(screen.getByTestId('compare-row-cost.gateway').textContent).toContain(
      '≠ methods differ',
    );
    expect(screen.getByTestId(`compare-cell-cost.gateway-${B}`).textContent).toContain(
      'cost.gateway@2',
    );
    expect(screen.getByTestId('compare-row-time.wall').textContent).not.toContain(
      '≠ methods differ',
    );
  });

  it('prints a harness delta only for a Run that has one', () => {
    const payload = comparePayload([A, B]);
    payload.metrics = [
      metric('cost.harness', [A, B], { harness_delta: { [A]: '+0.40 over gateway' } }),
    ];
    mount(payload);
    expect(screen.getByTestId(`compare-cell-cost.harness-${A}`).textContent).toContain(
      '+0.40 over gateway',
    );
    expect(screen.getByTestId(`compare-cell-cost.harness-${B}`).textContent).not.toContain(
      'over gateway',
    );
  });

  it('reads — for a Run with no run-scope value, a missing word as given, and opens the origin on click', () => {
    const payload = comparePayload([A, B]);
    payload.runs[0] = header(A, { subscription: true });
    payload.metrics = [
      metric('cost.gateway', [A, B], {
        cells: { [A]: [cell({ scope_key: A, value_num: '2' })], [B]: [] },
      }),
      metric('time.wall', [A, B], {
        cells: {
          [A]: [cell({ value_num: null, missing: 'not recorded', unit: 'seconds' })],
          [B]: [],
        },
      }),
    ];
    mount(payload);
    expect(screen.getByTestId(`compare-cell-cost.gateway-${B}`).textContent).toBe('—');
    expect(screen.getByTestId(`compare-cell-time.wall-${A}`).textContent).toContain('not recorded');
    fireEvent.click(
      within(screen.getByTestId(`compare-cell-cost.gateway-${A}`)).getByRole('button'),
    );
    const target = $originTarget.get();
    expect(target?.runLabel).toBe(payload.runs[0].label);
    expect(target?.subscription).toBe(true);
    expect(target?.value.metric_id).toBe('cost.gateway');
  });

  it('shows diff size per Run, with recalculate only for not run', () => {
    const payload = comparePayload([A, B]);
    payload.diff_size[B] = '+10 −2 · 3 files';
    mount(payload);
    expect(screen.getByTestId(`compare-diff-size-${A}`).textContent).toContain('not run');
    const link = within(screen.getByTestId(`compare-diff-size-${A}`)).getByText('recalculate');
    expect(link.getAttribute('href')).toBe(`/workflows/${A}?tab=metrics&recalculate=1`);
    expect(screen.getByTestId(`compare-diff-size-${B}`).textContent).toBe('+10 −2 · 3 files');
    expect(within(screen.getByTestId(`compare-col-${B}`)).queryByText('recalculate')).toBeNull();
  });
});

describe('CompareHeader', () => {
  it('has no version segments for a Run with no versions, and no recalculate for a sized diff', () => {
    render(
      createElement(
        'table',
        null,
        createElement(
          'thead',
          null,
          createElement(
            'tr',
            null,
            createElement(CompareHeader, {
              header: header(A, { versions_available: [], selected_version: null }),
              canRemove: true,
              diffSize: '+1 −1',
              onRemove,
              onVersion,
            }),
          ),
        ),
      ),
    );
    expect(screen.queryByTestId(`compare-version-${A}-1`)).toBeNull();
    expect(screen.queryByText('recalculate')).toBeNull();
    fireEvent.click(screen.getByTestId(`compare-remove-${A}`));
    expect(onRemove).toHaveBeenCalledWith(A);
  });
});
