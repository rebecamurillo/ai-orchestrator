/**
 * `StepsTable.tsx` (4.15, UX-DR16): every planned row from `steps[]`, from the start, the
 * current row promoted, a skipped row's own reason, and no colour but the token
 * (`renderToStaticMarkup`, stateless).
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import StepsTable from '../../src/components/run/StepsTable';
import type { RunDetailOut, StepRowOut } from '../../src/lib/run/detail';

function row(overrides: Partial<StepRowOut> = {}): StepRowOut {
  return {
    seq: 1,
    path: 'plan',
    label: 'plan',
    kind: 'plan.check',
    gate: 'deterministic',
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

describe('StepsTable', () => {
  it('lists all 12 planned rows by path with their tokens, row 5 promoted', () => {
    const steps = Array.from({ length: 12 }, (_, i) =>
      row({
        seq: i + 1,
        path: `row-${i + 1}`,
        token: i + 1 === 5 ? 'RUN' : 'QUE',
        status: i + 1 === 5 ? 'running' : 'planned',
      }),
    );
    const html = renderToStaticMarkup(createElement(StepsTable, { detail: detail(steps) }));

    for (let i = 1; i <= 12; i += 1) {
      expect(html).toContain(`data-testid="wf-step-${i}"`);
      expect(html).toContain(`row-${i}`);
    }
    expect(html).toContain('data-current="true"');
    // exactly one row is promoted
    expect(html.match(/data-current="true"/g)?.length).toBe(1);
  });

  it('reads skipped · {reason} in grey for a skipped row', () => {
    const html = renderToStaticMarkup(
      createElement(StepsTable, {
        detail: detail([
          row({ status: 'skipped', token: 'SKP', reason: 'no quality_gate_command' }),
        ]),
      }),
    );

    expect(html).toContain('SKP · skipped — no quality_gate_command');
    expect(html).toContain('data-signal="neutral"');
  });

  it('shows the attempt count only above one', () => {
    const single = renderToStaticMarkup(
      createElement(StepsTable, { detail: detail([row({ attempts: 1 })]) }),
    );
    const many = renderToStaticMarkup(
      createElement(StepsTable, { detail: detail([row({ attempts: 3 })]) }),
    );

    expect(single).not.toContain('attempts');
    expect(many).toContain('· 3 attempts');
  });

  it("colours a running row's token green", () => {
    const html = renderToStaticMarkup(
      createElement(StepsTable, { detail: detail([row({ status: 'running', token: 'RUN' })]) }),
    );

    expect(html).toContain('data-signal="run"');
  });
});
