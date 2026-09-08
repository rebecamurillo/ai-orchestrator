/**
 * `CostBlock.tsx`'s 5.10 additions — the `provisional` marker on spent/budget and the
 * `trace` row linking `open in Langfuse` — kept apart from the frozen `run-cost-block.
 * test.ts`, whose own `not.toContain('trace')` assertion (a null `trace_url`) this file
 * must keep true, and whose trace-link case predates the `wf-trace` test-id and the "open in
 * Langfuse" link text.
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

describe('CostBlock · provisional', () => {
  it('reads the ratio plain when nothing is provisional', () => {
    const html = renderToStaticMarkup(createElement(CostBlock, { detail: detail() }));

    expect(html).toContain('$12.30 / $40.00');
    expect(html).not.toContain('data-testid="wf-cost-provisional"');
  });

  it('marks the ratio provisional when the cost read is an estimate', () => {
    const html = renderToStaticMarkup(
      createElement(CostBlock, { detail: detail({ provisional: true }) }),
    );

    expect(html).toContain('data-testid="wf-cost-provisional"');
    expect(html).toContain('$12.30 / $40.00');
    expect(html).toContain('provisional');
  });
});

describe('CostBlock · trace', () => {
  it('shows the open in Langfuse link when a trace exists', () => {
    const html = renderToStaticMarkup(
      createElement(CostBlock, { detail: detail({ trace_url: 'https://langfuse.example/t/1' }) }),
    );

    expect(html).toContain('data-testid="wf-trace"');
    expect(html).toContain('href="https://langfuse.example/t/1"');
    expect(html).toContain('open in Langfuse');
  });

  it('shows no trace row at all when trace_url is null', () => {
    const html = renderToStaticMarkup(createElement(CostBlock, { detail: detail() }));

    expect(html).not.toContain('data-testid="wf-trace"');
    expect(html).not.toContain('trace');
  });
});
