// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import { metricsContext } from '../../src/components/run/MetricsTab';
import StaticSignals from '../../src/components/run/StaticSignals';
import { NotAvailable } from '../../src/components/run/StaticSignalsRows';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { $originTarget } from '../../src/stores/metric-ui';
import { $runAnalysis } from '../../src/stores/run-analysis';
import { detailOf, glanceOf } from './run-metrics-fixtures';
import { analysis } from './static-fixtures';
import {
  BUG,
  COVERAGE,
  LINT,
  SECURITY,
  opengrepAnalysis,
  run,
  tierEntries,
} from './static-tier-fixtures';

const ctx = metricsContext(detailOf(), glanceOf(), false);
const partial = { missing: 'partial', partial_n: 1, partial_m: 2 };
const items = [
  run(LINT, null, '3', partial),
  run(LINT, null, null, {
    scope_type: 'repository',
    scope_key: '.',
    missing: 'n/a — tier 2 not declared',
  }),
  run(LINT, null, '3', { scope_type: 'repository', scope_key: 'repos/app' }),
  run(COVERAGE, 'covered', '30', partial),
  run(COVERAGE, 'instrumented', '40', partial),
  run(SECURITY, 'high', '3', partial),
  run(SECURITY, 'medium', '0', partial),
  run(SECURITY, 'low', '0', partial),
  run(SECURITY, 'fixed', '1', partial),
  run(SECURITY, 'unchanged', '2', partial),
];
const two = [analysis(), opengrepAnalysis()];

const mount = (shown = items) =>
  render(createElement(StaticSignals, { runId: 'r1', shown: 1, items: shown, ctx, set: 'all' }));

beforeEach(() => {
  GET.mockReset();
  $runAnalysis.set({ runId: '', version: null, status: 'idle', items: [], failed: null });
  $catalogue.set({
    status: 'ready',
    entries: Object.fromEntries(tierEntries().map((e) => [e.id, e])),
  });
  GET.mockResolvedValue({ data: { run_id: 'r1', version: 1, items: two, step_entries: [] } });
});
afterEach(() => {
  cleanup();
  resetCatalogue();
  $originTarget.set(null);
});

describe('Tier 2 on the Run page', () => {
  it('prints the partial word on each Run cell and the stored word on the repository', async () => {
    mount();
    const row = await screen.findByTestId(`static-row-run-${LINT}`);
    expect(row.textContent).toContain('3');
    expect(row.textContent).toContain('partial · 1 of 2 repositories');
    expect(screen.getByTestId(`static-row-.-${LINT}`).textContent).toContain(
      'n/a — tier 2 not declared',
    );
    expect(screen.getByTestId(`static-row-repos/app-${LINT}`).textContent).not.toContain('partial');
    expect(screen.getByTestId(`static-row-run-${COVERAGE}`).textContent).toContain('covered');
  });

  it('reads 3 possible high with the other severities and states', async () => {
    mount();
    const text = (await screen.findByTestId(`static-row-run-${SECURITY}`)).textContent!;
    expect(text).toContain('3 possible high');
    expect(text).toContain('0 possible medium');
    expect(text).toContain('0 possible low');
    expect(text).toContain('fixed 1');
    expect(text).toContain('unchanged 2');
  });

  it('opens the drawer target with the opengrep findings source and its kind', async () => {
    mount();
    const row = await screen.findByTestId(`static-row-run-${SECURITY}`);
    fireEvent.click(
      within(row)
        .getAllByRole('button')
        .find((b) => b.className.includes('metric-value-cell'))!,
    );
    expect($originTarget.get()?.findings).toEqual([
      {
        runId: 'r1',
        analysisId: 'an-app',
        tool: 'opengrep',
        repository: 'repos/app',
        kind: 'security',
      },
    ]);
  });

  it('gives a bug finding the bug kind', async () => {
    mount([run(BUG, 'high', '1')]);
    const row = await screen.findByTestId(`static-row-run-${BUG}`);
    fireEvent.click(
      within(row)
        .getAllByRole('button')
        .find((b) => b.className.includes('metric-value-cell'))!,
    );
    expect($originTarget.get()?.findings?.[0]?.kind).toBe('bug');
  });

  it('reads one n/a row in each of the two blocks without a Tier 2 or Tier 3 value', async () => {
    mount([]);
    await screen.findByTestId('static-signals-table');
    expect(screen.getAllByText('n/a')).toHaveLength(2);
    expect(screen.getByText('TIER 2 · OPT-IN')).toBeTruthy();
    expect(screen.getByTestId('static-foot').textContent).toContain(
      'rule packs: opengrep abcdef12',
    );
  });
});

describe('StaticSignalsRows alone', () => {
  it('prints the head and one n/a row', () => {
    render(
      createElement(
        'table',
        null,
        createElement('tbody', null, createElement(NotAvailable, { head: 'TIER 2 · OPT-IN' })),
      ),
    );
    expect(screen.getByText('TIER 2 · OPT-IN')).toBeTruthy();
    expect(screen.getByText('n/a')).toBeTruthy();
  });
});
