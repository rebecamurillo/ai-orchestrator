// @vitest-environment jsdom
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import StaticSignals from '../../src/components/run/StaticSignals';
import { metricsContext } from '../../src/components/run/MetricsTab';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { $originTarget } from '../../src/stores/metric-ui';
import { $runAnalysis } from '../../src/stores/run-analysis';
import { detailOf, glanceOf } from './run-metrics-fixtures';
import { DUP, SECRETS, SUPP, analysis, code, codeEntries } from './static-fixtures';

const ctx = metricsContext(detailOf(), glanceOf(), false);
const items = [
  code(SECRETS, { scope_type: 'repository', scope_key: '.' }),
  code(SUPP, { source: 'production', value_num: '3' }),
  code(SUPP, { source: 'per_100', value_num: null, missing: 'raw only' }),
  code(DUP, { source: 'production', value_num: '5' }),
  code(DUP, { source: 'small_change', value_num: null, missing: 'small change' }),
];
const two = [
  analysis({ sarif_tools: ['gitleaks'] }),
  analysis({ analysis_id: 'an-2', repository_path: 'repos/app', commits_outside_run: 2 }),
];

const mount = (shownItems = items, set: 'headline' | 'all' = 'all') =>
  render(createElement(StaticSignals, { runId: 'r1', shown: 1, items: shownItems, ctx, set }));

beforeEach(() => {
  GET.mockReset();
  $runAnalysis.set({ runId: '', version: null, status: 'idle', items: [], failed: null });
  $catalogue.set({
    status: 'ready',
    entries: Object.fromEntries(codeEntries().map((e) => [e.id, e])),
  });
});
afterEach(() => {
  cleanup();
  resetCatalogue();
  $originTarget.set(null);
});

const serve = (list: unknown[]) =>
  GET.mockResolvedValue({ data: { run_id: 'r1', version: 1, items: list } });

describe('StaticSignals', () => {
  it('prints the Run row, a row per repository, the detail lines and the tier heads', async () => {
    serve(two);
    mount();
    await screen.findByTestId('static-signals-table');
    expect(GET).toHaveBeenCalledWith('/runs/{run_id}/analysis', {
      params: { path: { run_id: 'r1' }, query: { v: 1 } },
    });
    expect(screen.getByText('STATIC SIGNALS ON THE CHANGE')).toBeTruthy();
    const scopes = screen
      .getAllByTestId(/^static-scope-/)
      .map((n) => n.getAttribute('data-testid'));
    expect(scopes.slice(0, 3)).toEqual([
      'static-scope-run',
      'static-scope-.',
      'static-scope-repos/app',
    ]);
    expect(screen.getAllByText(/base bbbbbbb \(merge base with main\)/)).toHaveLength(4);
    expect(screen.getAllByText(/head holds 2 commits this Run did not make/)).toHaveLength(2);
    expect(screen.getByText('TIER 1A · OFFLINE')).toBeTruthy();
    expect(screen.getByText('TIER 1B · LOOKUPS 2026-11-13')).toBeTruthy();
    expect(screen.getByText('TIER 2 · OPT-IN')).toBeTruthy();
    expect(screen.getByText('TIER 3 · FROM WORKFLOW STEPS')).toBeTruthy();
    expect(screen.getAllByText('n/a')).toHaveLength(2);
  });

  it('prints the footer without any interaction', async () => {
    serve(two);
    mount();
    const foot = await screen.findByTestId('static-foot');
    expect(foot.textContent).toContain('tools: gitleaks 8.30.1 · jscpd 4.0.5 · lizard 1.17');
    expect(foot.textContent).toContain('vulnerability database 2026-11-12');
    expect(foot.textContent).toContain('registry lookup 2026-11-13');
  });

  it('prints raw only and small change as stored words', async () => {
    serve(two);
    mount();
    const row = await screen.findByTestId(`static-row-run-${SUPP}`);
    const cells = within(row).getAllByRole('cell');
    expect(cells[1].textContent).toContain('3');
    expect(cells[2].textContent).toContain('raw only');
    const dup = screen.getByTestId(`static-row-run-${DUP}`);
    expect(dup.textContent).toContain('5');
    expect(dup.textContent).toContain('small change');
  });

  it('labels raw sources when a row has more than one', async () => {
    serve(two);
    mount([
      code(SUPP, { source: 'production', value_num: '3' }),
      code(SUPP, { source: 'test', value_num: '1' }),
    ]);
    const row = await screen.findByTestId(`static-row-run-${SUPP}`);
    expect(row.textContent).toContain('production');
    expect(row.textContent).toContain('test');
  });

  it('prints the not-run line when the version holds no analysis and no code value', async () => {
    serve([]);
    mount([]);
    expect(await screen.findByText('not run in v1 · RECALCULATE METRICS runs it')).toBeTruthy();
    expect(screen.queryByTestId('static-signals-table')).toBeNull();
  });

  it('prints a table with no footer when only code values exist', async () => {
    serve([]);
    mount();
    await screen.findByTestId('static-signals-table');
    expect(screen.queryByTestId('static-foot')).toBeNull();
    expect(screen.getByText('TIER 1B · LOOKUPS not run')).toBeTruthy();
  });

  it('names a failed read and retries on request', async () => {
    GET.mockResolvedValueOnce({ data: undefined, response: { status: 500 } });
    mount();
    const retry = await screen.findByRole('button', { name: /retry/i });
    expect(screen.getByText(/\/api\/runs\/r1\/analysis\?v=1/)).toBeTruthy();
    serve(two);
    await act(async () => {
      fireEvent.click(retry);
    });
    await screen.findByTestId('static-signals-table');
    expect(GET).toHaveBeenCalledTimes(2);
  });

  it('shows a loading mark while the read is in flight', () => {
    GET.mockReturnValue(new Promise(() => undefined));
    mount();
    expect(screen.getByText('…')).toBeTruthy();
  });

  it('opens a secrets value with the findings of the SARIF sources', async () => {
    serve(two);
    mount();
    const row = await screen.findByTestId(`static-row-.-${SECRETS}`);
    fireEvent.click(
      within(row)
        .getAllByRole('button')
        .find((b) => b.className.includes('metric-value-cell'))!,
    );
    expect($originTarget.get()?.findings).toEqual([
      { runId: 'r1', analysisId: 'an-1', tool: 'gitleaks', repository: '.' },
    ]);
  });

  it('opens a Run-row secrets value with every repository that holds a report', async () => {
    serve(two);
    mount([code(SECRETS)]);
    const row = await screen.findByTestId(`static-row-run-${SECRETS}`);
    fireEvent.click(
      within(row)
        .getAllByRole('button')
        .find((b) => b.className.includes('metric-value-cell'))!,
    );
    expect($originTarget.get()?.findings).toHaveLength(1);
  });

  it('adds no findings to a value without a tool', async () => {
    serve(two);
    mount();
    const row = await screen.findByTestId(`static-row-run-${SUPP}`);
    fireEvent.click(
      within(row)
        .getAllByRole('button')
        .find((b) => b.className.includes('metric-value-cell'))!,
    );
    expect($originTarget.get()?.findings).toBeUndefined();
  });
});
