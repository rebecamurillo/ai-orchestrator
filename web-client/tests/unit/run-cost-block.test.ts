/**
 * `CostBlock.tsx` (4.15): spent/budget as a ratio, tokens, wall-clock, active time as `—`,
 * the trace link only when one exists, the compare links, and the branch link
 * (`renderToStaticMarkup`, stateless).
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import CostBlock from '../../src/components/run/CostBlock';
import type { RunDetailOut } from '../../src/lib/run/detail';

function detail(
  overrides: Partial<RunDetailOut['run']> = {},
  trace_url: string | null = null,
): RunDetailOut {
  return {
    run: {
      id: '1',
      status: 'done',
      admitted_signals: [],
      branch: 'chore/x',
      budget_usd: '15',
      compare_urls: ['https://github.com/o/r/compare/main...chore/x'],
      created_at: '2026-09-07T09:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: 'p1',
      repository: 'r1',
      spend_usd: '4.18',
      template: 'initiative',
      terminal_session: false,
      version: 1,
      worktree_path: null,
      worktrees: [],
      accepted_paths: [],
      ...overrides,
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
      spent_usd: '4.18',
      budget_usd: '15.00',
      tokens_in: 100,
      tokens_out: 200,
      wall_clock_seconds: 90,
      active_seconds: 30,
      provisional: false,
      trace_url,
    },
    gate_record: [],
    admitted_signals: [],
    summary: null,
  };
}

describe('CostBlock', () => {
  it('shows the ratio, tokens, wall-clock and active time as an em dash', () => {
    const html = renderToStaticMarkup(createElement(CostBlock, { detail: detail() }));

    expect(html).toContain('data-testid="wf-cost"');
    expect(html).toContain('$4.18 / $15.00');
    expect(html).toContain('100 in / 200 out');
    expect(html).toContain('1m');
    expect(html).toContain('—');
  });

  it('omits the trace link this epic (always null)', () => {
    expect(renderToStaticMarkup(createElement(CostBlock, { detail: detail() }))).not.toContain(
      'trace',
    );
  });

  it('shows the trace link when one is present', () => {
    const html = renderToStaticMarkup(
      createElement(CostBlock, { detail: detail({}, 'https://trace.example/1') }),
    );

    expect(html).toContain('href="https://trace.example/1"');
  });

  it('lists the compare links and the derived branch link', () => {
    const html = renderToStaticMarkup(createElement(CostBlock, { detail: detail() }));

    expect(html).toContain('href="https://github.com/o/r/compare/main...chore/x"');
    expect(html).toContain('href="https://github.com/o/r/tree/chore/x"');
  });

  it('omits the branch link before any compare URL exists', () => {
    const html = renderToStaticMarkup(
      createElement(CostBlock, { detail: detail({ compare_urls: [] }) }),
    );

    expect(html).not.toContain('/tree/');
  });
});
