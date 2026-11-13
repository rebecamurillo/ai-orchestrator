// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import MetricsHome from '../../src/islands/MetricsHome';
import { resetCatalogue } from '../../src/stores/catalogue';
import { entry } from './metrics-fixtures';

const P = 'pppppppp-0000-7000-8000-000000000001';
const A = 'aaaaaaaa-0000-7000-8000-000000000001';
const B = 'bbbbbbbb-0000-7000-8000-000000000002';
const R = 'cccccccc-0000-7000-8000-000000000003';

const run = (id: string, over: Record<string, unknown> = {}) => ({
  base_branch: 'main',
  branch: 'b',
  gateway: '1',
  harness: 'claude',
  harness_spend: '1',
  id,
  label: `label ${id.slice(0, 1)}`,
  label_set_by_operator: false,
  latest_version: 1,
  selectable: true,
  status: 'done',
  subscription: null,
  template_name: 't',
  template_version: 1,
  wall_clock_seconds: 5,
  ...over,
});

const spendItem = {
  cancelled: { gateway: '0', harness: '0', runs: 0 },
  gateway: '3',
  gateway_reported: true,
  harness: '2',
  harness_reported: true,
  project_id: P,
  project_name: 'Proj',
  runs: 3,
  subscription: null,
};

interface Plan {
  runs?: unknown;
  spend?: unknown;
}
function plan({ runs, spend }: Plan) {
  GET.mockImplementation((path: string) => {
    if (path === '/metrics/catalogue')
      return Promise.resolve({ data: { items: [entry('spend.month')], next_cursor: null } });
    const body = path === '/metrics/runs' ? runs : spend;
    if (body === 'fail') return Promise.resolve({ error: {}, response: { status: 500 } });
    if (body === 'reject') return Promise.reject(new Error('net'));
    return Promise.resolve({ data: body, response: { status: 200 } });
  });
}
const okRuns = {
  items: [
    run(R, { status: 'running', selectable: false, latest_version: null }),
    run(A),
    run(B, { status: 'cancelled', latest_version: null }),
  ],
  next_cursor: null,
};
const okSpend = { items: [spendItem] };
const paths = () => GET.mock.calls.map((c) => c[0]);

beforeEach(() => window.history.replaceState(null, '', '/metrics'));
afterEach(() => {
  cleanup();
  resetCatalogue();
  GET.mockReset();
});

const mount = (props: { projectId: string | null; select?: string[] }) =>
  render(
    createElement(MetricsHome, {
      projectName: props.projectId ? 'Proj' : null,
      select: [],
      ...props,
    }),
  );

describe('MetricsHome', () => {
  it('without a project reads no runs and still shows spend', async () => {
    plan({ spend: okSpend });
    mount({ projectId: null });
    await screen.findByTestId('metrics-spend-table');
    expect(screen.getByTestId('metrics-no-project').textContent).toBe(
      'choose a project above to list its Runs',
    );
    expect(paths()).not.toContain('/metrics/runs');
  });

  it('lists runs with two boxes and one running word', async () => {
    plan({ runs: okRuns, spend: okSpend });
    mount({ projectId: P });
    await screen.findByTestId('metrics-runs-table');
    expect(screen.getByText('RUNS · Proj')).toBeTruthy();
    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
    expect(screen.getAllByText('running')).toHaveLength(1);
    expect(GET).toHaveBeenCalledWith('/metrics/runs', { params: { query: { project: P } } });
  });

  it('keeps tick order in the link and the URL, and clears', async () => {
    plan({ runs: okRuns, spend: okSpend });
    mount({ projectId: P });
    await screen.findByTestId('metrics-runs-table');
    fireEvent.click(screen.getByTestId(`metrics-run-select-${B}`));
    fireEvent.click(screen.getByTestId(`metrics-run-select-${A}`));
    expect(screen.getByTestId('metrics-selection-count').textContent).toBe('2 selected');
    expect(screen.getByTestId('metrics-compare').getAttribute('href')).toBe(
      `/metrics/compare?runs=${B},${A}`,
    );
    expect(window.location.search).toBe(`?project=${P}&select=${B},${A}`);
    fireEvent.click(screen.getByTestId('metrics-clear'));
    expect(screen.getByTestId('metrics-selection-count').textContent).toBe('0 selected');
    expect(window.location.search).toBe(`?project=${P}`);
  });

  it('prunes unknown and non-selectable ids from the URL select', async () => {
    plan({ runs: okRuns, spend: okSpend });
    mount({ projectId: P, select: [A, 'x', R] });
    await screen.findByTestId('metrics-runs-table');
    expect(screen.getByTestId(`metrics-run-select-${A}`).getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('metrics-selection-count').textContent).toBe('1 selected');
  });

  it.each(['fail', 'reject'])('isolates a runs read that %ss, and retries it', async (mode) => {
    plan({ runs: mode, spend: okSpend });
    mount({ projectId: P });
    await screen.findByTestId('metrics-runs-failed');
    expect(screen.getByTestId('metrics-spend-table')).toBeTruthy();
    plan({ runs: okRuns, spend: okSpend });
    fireEvent.click(screen.getByTestId('metrics-runs-retry'));
    await screen.findByTestId('metrics-runs-table');
  });

  it.each(['fail', 'reject'])('isolates a spend read that %ss, and retries it', async (mode) => {
    plan({ runs: okRuns, spend: mode });
    mount({ projectId: P });
    await screen.findByTestId('metrics-spend-failed');
    expect(screen.getByTestId('metrics-runs-table')).toBeTruthy();
    plan({ runs: okRuns, spend: okSpend });
    fireEvent.click(screen.getByTestId('metrics-spend-retry'));
    await waitFor(() => expect(screen.getByTestId('metrics-spend-table')).toBeTruthy());
  });
});
