/**
 * `Banner.tsx`'s 5.10 signal rule: a `blocked` detail's top banner stays neutral — the
 * Question block's own left rule and the current Stories-strip cell are the only amber
 * elements a `blocked` detail shows. The frozen `run-banner.test.ts` only ever exercises
 * `park_kind: 'plan_stale'`, so this is new coverage of a case it never reaches.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import Banner from '../../src/components/run/Banner';
import type { RunDetailOut } from '../../src/lib/run/detail';

function base(): RunDetailOut {
  return {
    run: {
      id: '1',
      status: 'needs_you',
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
      spend_usd: '4.18',
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
    alert: { token: 'BLK', reason: '## Auto Run Result', park_kind: 'blocked' },
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
    summary: null,
  };
}

describe('Banner · blocked stays neutral', () => {
  it('reads data-signal="neutral", not "needs-you", for a blocked park', () => {
    const html = renderToStaticMarkup(createElement(Banner, { detail: base(), token: 'BLK' }));

    expect(html).toContain('data-testid="wf-alert"');
    expect(html).toContain('data-signal="neutral"');
    expect(html).not.toContain('data-signal="needs-you"');
  });

  it('still reads needs-you amber for every other park kind (unchanged)', () => {
    const detail: RunDetailOut = {
      ...base(),
      alert: { token: 'BLK', reason: 'timeout', park_kind: 'timeout' },
    };

    const html = renderToStaticMarkup(createElement(Banner, { detail, token: 'BLK' }));

    expect(html).toContain('data-signal="needs-you"');
  });
});
