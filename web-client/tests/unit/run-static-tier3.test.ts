// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import { metricsContext } from '../../src/components/run/MetricsTab';
import StaticSignals from '../../src/components/run/StaticSignals';
import StaticTierThree from '../../src/components/run/StaticTierThree';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { $originTarget } from '../../src/stores/metric-ui';
import { $runAnalysis } from '../../src/stores/run-analysis';
import { detailOf, glanceOf } from './run-metrics-fixtures';
import { analysis } from './static-fixtures';
import {
  FIRST,
  HELDOUT,
  LIMITS,
  firstEntry,
  run,
  stepEntry,
  tierEntries,
} from './static-tier-fixtures';

const ctx = metricsContext(detailOf(), glanceOf(), false);
const first = [
  run(FIRST, 'test_first', '4', { unit: 'stories' }),
  run(FIRST, 'test_with_code', '2', { unit: 'stories' }),
  run(FIRST, 'test_after', '0', { unit: 'stories' }),
  run(FIRST, 'not_readable', '2', { unit: 'stories' }),
  run(FIRST, 'readable', '6', { unit: 'stories' }),
  run(FIRST, 'stories', '8', { unit: 'stories' }),
];
const steps = [run(HELDOUT, 'passed', '18'), run(HELDOUT, 'failed', '2')];

const serve = (list: unknown[], stepEntries: unknown[] = []) =>
  GET.mockResolvedValue({
    data: { run_id: 'r1', version: 1, items: list, step_entries: stepEntries },
  });
const mount = (items: ReturnType<typeof run>[]) =>
  render(createElement(StaticSignals, { runId: 'r1', shown: 1, items, ctx, set: 'all' }));

beforeEach(() => {
  GET.mockReset();
  $runAnalysis.set({ runId: '', version: null, status: 'idle', items: [], failed: null });
  $catalogue.set({
    status: 'ready',
    entries: Object.fromEntries([...tierEntries(), firstEntry()].map((e) => [e.id, e])),
  });
});
afterEach(() => {
  cleanup();
  resetCatalogue();
  $originTarget.set(null);
});

describe('Tier 3 on the Run page', () => {
  it('prints the test-first line from the stored counts, outcomes beside it, hint with limits', async () => {
    serve([analysis()]);
    mount(first);
    const line = await screen.findByText(
      'test-first order · method followed, not quality · 6 of 8 stories readable from the logs',
    );
    const row = line.closest('tr')!;
    expect(row.textContent).toContain('test first');
    expect(row.textContent).toContain('test with code');
    expect(row.textContent).toContain('not readable');
    fireEvent.click(
      row.querySelector('button.metric-hint-control, button[aria-haspopup], button')!,
    );
    expect(await screen.findByText(LIMITS)).toBeTruthy();
    expect(screen.getByText('TIER 3 · FROM WORKFLOW STEPS')).toBeTruthy();
  });

  it('prints a step-produced metric by its label and opens its origin', async () => {
    serve([analysis()], [stepEntry()]);
    mount(steps);
    const label = await screen.findByText('held-out tests');
    const row = label.closest('tr')!;
    expect(row.textContent).toContain('passed 18');
    expect(row.textContent).toContain('failed 2');
    expect(row.textContent).toContain(' · ');
    fireEvent.click(row.querySelector('.metric-value-cell')!);
    expect($originTarget.get()?.value.metric_id).toBe(HELDOUT);
  });

  it('prints the not-run line with the test-first line under it when nothing was analysed', async () => {
    serve([]);
    mount(first);
    expect(await screen.findByText('not run in v1 · RECALCULATE METRICS runs it')).toBeTruthy();
    expect(screen.getByText(/6 of 8 stories readable from the logs/)).toBeTruthy();
    expect(screen.queryByText('TIER 2 · OPT-IN')).toBeNull();
  });

  it('prints the plain test-first words when the counts are not stored', async () => {
    serve([analysis()]);
    mount(first.slice(0, 4));
    expect(await screen.findByText('test-first order · method followed, not quality')).toBeTruthy();
  });

  it('prints a step entry without values as a dash row', async () => {
    serve([analysis()], [stepEntry()]);
    mount(first);
    const label = await screen.findByText('held-out tests');
    expect(label.closest('tr')!.textContent).toContain('—');
  });
});

describe('StaticTierThree alone', () => {
  it('reads one n/a row without a test-first row or a step value', () => {
    render(
      createElement(
        'table',
        null,
        createElement(
          'tbody',
          null,
          createElement(StaticTierThree, { items: [], stepEntries: [], set: 'all', ctx }),
        ),
      ),
    );
    expect(screen.getByText('TIER 3 · FROM WORKFLOW STEPS')).toBeTruthy();
    expect(screen.getByText('n/a')).toBeTruthy();
  });
});
