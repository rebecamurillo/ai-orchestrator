/**
 * `StepsTable.tsx`'s 5.10 cost-column fix: the cell reads the row's own summed `cost_usd`
 * (5.3), not the latest attempt's, with `provisional` after it when that latest attempt's
 * own cost is still an estimate. The frozen `run-steps-table.test.ts` asserts nothing about
 * the cost cell's text, so this is new coverage, not a conflicting one.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import StepsTable from '../../src/components/run/StepsTable';
import type { RunDetailOut, StepRowOut } from '../../src/lib/run/detail';

function row(overrides: Partial<StepRowOut> = {}): StepRowOut {
  return {
    seq: 1,
    path: 'stories[0].build',
    label: 'build',
    kind: 'agent',
    gate: 'liveness',
    status: 'done',
    token: 'DON',
    reason: null,
    attempts: 1,
    latest: null,
    cost_usd: '0.00',
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
      created_at: '2026-09-07T09:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: 'p1',
      repository: 'r1',
      spend_usd: '0',
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

describe('StepsTable · cost column', () => {
  it("reads the row's own summed cost_usd, not the latest attempt's own", () => {
    const html = renderToStaticMarkup(
      createElement(StepsTable, {
        detail: detail([
          row({
            cost_usd: '1.23',
            latest: {
              n: 2,
              started_at: null,
              ended_at: null,
              seconds: null,
              harness: 'claude',
              model: 'claude-opus-4',
              exit_code: 0,
              cost_usd: '0.40',
              log_tail: [],
            },
          }),
        ]),
      }),
    );

    expect(html).toContain('$1.23');
    expect(html).not.toContain('$0.40');
  });

  it("reads provisional after the row's cost when the latest attempt is provisional", () => {
    const html = renderToStaticMarkup(
      createElement(StepsTable, {
        detail: detail([
          row({
            cost_usd: '1.23',
            latest: {
              n: 1,
              started_at: null,
              ended_at: null,
              seconds: null,
              harness: 'claude',
              model: 'claude-opus-4',
              exit_code: 0,
              cost_usd: '1.23',
              log_tail: [],
              cost_provisional: true,
            },
          }),
        ]),
      }),
    );

    expect(html).toContain('$1.23 provisional');
  });

  it('reads no provisional word when the latest attempt is settled', () => {
    const html = renderToStaticMarkup(
      createElement(StepsTable, {
        detail: detail([
          row({
            cost_usd: '1.23',
            latest: {
              n: 1,
              started_at: null,
              ended_at: null,
              seconds: null,
              harness: 'claude',
              model: 'claude-opus-4',
              exit_code: 0,
              cost_usd: '1.23',
              log_tail: [],
              cost_provisional: false,
            },
          }),
        ]),
      }),
    );

    expect(html).toContain('$1.23');
    expect(html).not.toContain('provisional');
  });

  it('reads $0.00 for a row with no attempts yet', () => {
    const html = renderToStaticMarkup(
      createElement(StepsTable, { detail: detail([row({ cost_usd: '0.00', latest: null })]) }),
    );

    expect(html).toContain('$0.00');
  });
});
