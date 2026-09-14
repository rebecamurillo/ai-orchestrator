/**
 * `CostBlock.tsx` off-mode behavior (story 9-6): null `trace_url` and provisional cost
 * when the stack runs without LiteLLM Gateway or Langfuse.
 *
 * The components are correct from 9-2; these tests explicitly attribute the coverage to the
 * off-mode story so a future refactor of the general component tests cannot lose it.
 *
 * Kept apart from the frozen `run-cost-block-provisional.test.ts` (ANCHOR READ-ONLY).
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import CostBlock from '../../src/components/run/CostBlock';
import type { RunDetailOut } from '../../src/lib/run/detail';

function detail(costOverrides: Partial<RunDetailOut['cost']> = {}): RunDetailOut {
  return {
    run: {
      id: '1',
      status: 'done',
      admitted_signals: [],
      branch: 'chore/x',
      budget_usd: '40.00',
      compare_urls: [],
      created_at: '2026-09-07T09:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: 'p1',
      repository: 'r1',
      spend_usd: '12.30',
      template: 'initiative',
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
        template: 'initiative',
        version: 1,
        harness: 'claude',
        started_at: null,
        worktree_path: null,
      },
    },
    alert: null,
    steps: [],
    stories: [],
    cost: {
      spent_usd: '12.30',
      budget_usd: '40.00',
      tokens_in: 100,
      tokens_out: 200,
      wall_clock_seconds: 90,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
      ...costOverrides,
    },
    gate_record: [],
    admitted_signals: [],
    summary: null,
  };
}

describe('CostBlock · off-mode · null trace_url (Langfuse disabled)', () => {
  it('shows no trace row when trace_url is null', () => {
    const html = renderToStaticMarkup(createElement(CostBlock, { detail: detail() }));

    expect(html).not.toContain('data-testid="wf-trace"');
    expect(html).not.toContain('open in Langfuse');
  });
});

describe('CostBlock · off-mode · provisional cost (Gateway disabled)', () => {
  it('marks the ratio provisional when cost is the harness own estimate', () => {
    const html = renderToStaticMarkup(
      createElement(CostBlock, { detail: detail({ provisional: true }) }),
    );

    expect(html).toContain('data-testid="wf-cost-provisional"');
    expect(html).toContain('provisional');
  });
});
