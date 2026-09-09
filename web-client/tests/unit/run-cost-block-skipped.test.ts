/**
 * The compare-link line on a `done` Run that skipped a Story (6.4, FR-11, FR-20, SM-C3):
 * `{url} · skipped: {ids}`.
 *
 * Kept apart from the frozen `run-cost-block.test.ts`, which asserts the link's `href` and
 * the derived branch link — both still true, since only the anchor's *text* changed.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import CostBlock from '../../src/components/run/CostBlock';
import type { RunDetailOut } from '../../src/lib/run/detail';

const URL = 'https://github.com/o/r/compare/main...epics/gates';

function detail(summary: RunDetailOut['summary']): RunDetailOut {
  return {
    run: {
      id: '1',
      status: 'done',
      admitted_signals: [],
      branch: 'epics/gates',
      budget_usd: '15',
      compare_urls: [URL],
      created_at: '2026-09-07T09:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: 'p1',
      repository: 'r1',
      spend_usd: '4.18',
      template: 'epic',
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
        folder: 'specs/gates',
        template: 'epic',
        version: 1,
        harness: 'fake',
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
      tokens_in: 0,
      tokens_out: 0,
      wall_clock_seconds: 0,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: [],
    summary,
  } as unknown as RunDetailOut;
}

function render(summary: RunDetailOut['summary']): string {
  return renderToStaticMarkup(createElement(CostBlock, { detail: detail(summary) }));
}

describe('CostBlock · the skipped ids on the compare line', () => {
  it('names them after the url', () => {
    const html = render({ progress: null, links: [URL], skipped: ['2'] });

    expect(html).toContain(`${URL} · skipped: 2`);
    expect(html).toContain(`href="${URL}"`);
  });

  it('joins several ids', () => {
    const html = render({ progress: null, links: [URL], skipped: ['2', '4-3'] });

    expect(html).toContain(`${URL} · skipped: 2, 4-3`);
  });

  it('leaves the line as the bare url when nothing was skipped', () => {
    const html = render({ progress: null, links: [URL], skipped: [] });

    expect(html).toContain(`>${URL}</a>`);
    expect(html).not.toContain('skipped:');
  });

  it('leaves it alone before the Run is done and carries a summary', () => {
    const html = render(null);

    expect(html).toContain(`>${URL}</a>`);
    expect(html).not.toContain('skipped:');
  });
});
