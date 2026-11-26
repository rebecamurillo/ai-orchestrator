// @vitest-environment jsdom
/** Story 11.1: AutoWorkflowSummary (AC8, AC9, a failed read). */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import AutoWorkflowSummary from '../../src/components/initiative/AutoWorkflowSummary';
import { workflow } from './initiative-fixtures';

beforeEach(() => GET.mockReset());
afterEach(cleanup);

const build = (over = {}) =>
  workflow('build', 2, { type: 'auto', token: 'RUN', line: 'story 3 of 9', ...over });

const mount = (w = build({ run_id: 'run-9' })) =>
  render(createElement(AutoWorkflowSummary, { workflow: w, previous: 'spec', projectId: 'p1' }));

describe('AutoWorkflowSummary with a Run', () => {
  beforeEach(() => {
    GET.mockResolvedValue({
      data: {
        id: 'run-9',
        status: 'running',
        spend_usd: '12.50',
        budget_usd: '60.00',
        branch: 'feat/x',
        repository: 'familio-web',
        template: 'build-flow',
        version: 3,
      },
      response: { status: 200 },
    });
  });

  it('shows head, token, line, spend, branch, the fixed line and the open link', async () => {
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-open-workflow')).toBeTruthy());
    expect(GET).toHaveBeenCalledWith('/runs/{run_id}', {
      params: { path: { run_id: 'run-9' } },
    });
    const text = document.body.textContent ?? '';
    expect(text).toContain('WORKFLOW 2 · BUILD · AUTO · build-flow@3');
    expect(text).toContain('RUN');
    expect(text).toContain('story 3 of 9');
    expect(text).toContain('$12.50 / $60.00');
    expect(text).toContain('feat/x · familio-web');
    expect(text).toContain(
      "The diagram, the steps, the logs and the files per epic and story are on the workflow's own page. A stop of this workflow shows here as needs you, with its reason, and is answered there.",
    );
    const link = screen.getByTestId('ini-open-workflow');
    expect(link.getAttribute('href')).toBe('/workflows/run-9');
    expect(link.textContent).toBe('Open workflow');
  });

  it('shows spend alone without a budget', async () => {
    GET.mockResolvedValue({
      data: {
        id: 'run-9',
        status: 'running',
        spend_usd: '1.00',
        budget_usd: null,
        branch: 'b',
        repository: 'r',
        template: 't',
        version: 1,
      },
      response: { status: 200 },
    });
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-open-workflow')).toBeTruthy());
    expect(document.body.textContent).toContain('$1.00');
    expect(document.body.textContent).not.toContain('/ $');
  });

  it('renders a failed read inside the summary with a retry', async () => {
    GET.mockResolvedValueOnce({ error: {}, response: { status: 500 } });
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-summary-failed')).toBeTruthy());
    expect(document.body.textContent).toContain('/runs/run-9');
    fireEvent.click(screen.getByTestId('ini-summary-retry'));
    await waitFor(() => expect(screen.getByTestId('ini-open-workflow')).toBeTruthy());
  });

  it('renders a thrown read as failed', async () => {
    GET.mockRejectedValueOnce(new Error('down'));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-summary-failed')).toBeTruthy());
  });
});

describe('AutoWorkflowSummary without a Run', () => {
  const project = (budget: string | null) => ({
    data: {
      id: 'p1',
      default_autonomy: 'auto',
      default_model: 'claude-opus-5-5',
      default_budget_usd: budget,
    },
    response: { status: 200 },
  });

  it('states when it starts and the project defaults', async () => {
    GET.mockResolvedValue(project('60.00'));
    mount(build({ run_id: null, token: null }));
    await waitFor(() => expect(document.body.textContent).toContain('project defaults'));
    expect(GET).toHaveBeenCalledWith('/projects/{project_id}', {
      params: { path: { project_id: 'p1' } },
    });
    const text = document.body.textContent ?? '';
    expect(text).toContain('not started');
    expect(text).toContain('starts by itself when spec is done');
    expect(text).toContain('template build-flow@3 · auto');
    expect(text).toContain('project defaults: autonomy auto · claude-opus-5-5 · budget $60.00');
    expect(screen.queryByTestId('ini-open-workflow')).toBeNull();
  });

  it('states a missing default budget', async () => {
    GET.mockResolvedValue(project(null));
    mount(build({ run_id: null, token: null }));
    await waitFor(() =>
      expect(document.body.textContent).toContain(
        'no default budget — the build will stop and ask',
      ),
    );
  });

  it('shows the first lines without a project id and reads nothing', () => {
    render(
      createElement(AutoWorkflowSummary, {
        workflow: build({ run_id: null }),
        previous: null,
        projectId: null,
      }),
    );
    expect(GET).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain('not started');
  });

  it('renders a failed project read inside the summary', async () => {
    GET.mockResolvedValue({ error: {}, response: { status: 404 } });
    mount(build({ run_id: null }));
    await waitFor(() => expect(screen.getByTestId('ini-summary-failed')).toBeTruthy());
  });
});
