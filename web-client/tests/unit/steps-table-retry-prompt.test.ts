/**
 * `StepsTable.tsx` sub-row for `retry_prompt` (story 3-5):
 * renders `wf-step-{seq}-retry-prompt` when `retry_prompt` is non-null/non-empty;
 * omits it when absent.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import StepsTable from '../../src/components/run/StepsTable';
import type { RunDetailOut, StepRowOut } from '../../src/lib/run/detail';

function row(overrides: Partial<StepRowOut> = {}): StepRowOut {
  return {
    seq: 1,
    path: 'build',
    label: 'build',
    kind: 'agent',
    gate: 'liveness',
    status: 'planned',
    token: 'QUE',
    reason: null,
    attempts: 1,
    latest: null,
    ...overrides,
  };
}

function detail(steps: StepRowOut[]): RunDetailOut {
  return {
    run: {
      id: '1',
      status: 'running',
      admitted_signals: [],
      branch: 'epics/1',
      budget_usd: '15',
      compare_urls: [],
      created_at: '2026-09-17T09:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: 'p1',
      repository: 'r1',
      spend_usd: '0',
      template: 'story',
      terminal_session: false,
      version: 1,
      worktree_path: null,
      worktrees: [],
      accepted_paths: [],
    },
    header: {
      meta: {
        project: 'demo',
        repository: 'demo-repo',
        base_branch: 'main',
        folder: 'docs',
        template: 'story',
        version: 1,
        harness: 'claude',
        started_at: null,
        worktree_path: null,
      },
    },
    alert: null,
    steps,
    stories: [],
    cost: {
      spent_usd: '0',
      budget_usd: '15',
      tokens_in: 0,
      tokens_out: 0,
      wall_clock_seconds: 0,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: [],
    summary: null,
  };
}

describe('StepsTable retry_prompt sub-row', () => {
  it('renders wf-step-{seq}-retry-prompt when retry_prompt is set', () => {
    const html = renderToStaticMarkup(
      createElement(StepsTable, {
        detail: detail([row({ retry_prompt: 'try harder' })]),
      }),
    );

    expect(html).toContain('data-testid="wf-step-1-retry-prompt"');
    expect(html).toContain('try harder');
  });

  it('does not render wf-step-{seq}-retry-prompt when retry_prompt is absent', () => {
    const html = renderToStaticMarkup(createElement(StepsTable, { detail: detail([row()]) }));

    expect(html).not.toContain('retry-prompt');
  });

  it('does not render wf-step-{seq}-retry-prompt when retry_prompt is null', () => {
    const html = renderToStaticMarkup(
      createElement(StepsTable, {
        detail: detail([row({ retry_prompt: null })]),
      }),
    );

    expect(html).not.toContain('retry-prompt');
  });
});
