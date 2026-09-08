/**
 * `GateRecord.tsx`'s 5.10 signal rule: the last row's `■` marker carries no signal colour on
 * a `blocked` detail (`Banner.tsx`'s own comment explains why — the Question block's rule and
 * the current Stories-strip cell are the only amber a `blocked` detail shows). The frozen
 * `run-gate-record.test.ts` fixes `alert: null`, so it never reaches `park_kind: 'blocked'`.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import GateRecord from '../../src/components/run/GateRecord';
import type { GateRecordOut, RunDetailOut } from '../../src/lib/run/detail';

function detail(records: GateRecordOut[], parkKind: RunDetailOut['alert']): RunDetailOut {
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
    alert: parkKind,
    steps: [],
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
    gate_record: records,
    admitted_signals: [],
    summary: null,
  };
}

const RECORD: GateRecordOut = {
  id: 'g1',
  at: '2026-09-07T09:05:00Z',
  path: 'stories[0].build',
  event: 'blocked',
  actor: 'machine',
  text: '## Auto Run Result',
  attempt_n: null,
};

describe('GateRecord · blocked stays neutral', () => {
  it('carries no signal colour on the last row for a blocked park', () => {
    const html = renderToStaticMarkup(
      createElement(GateRecord, {
        detail: detail([RECORD], {
          token: 'BLK',
          reason: '## Auto Run Result',
          park_kind: 'blocked',
        }),
        token: 'BLK',
      }),
    );

    expect(html).not.toContain('data-signal');
  });

  it('still colours the last row for every other park kind (unchanged)', () => {
    const html = renderToStaticMarkup(
      createElement(GateRecord, {
        detail: detail([{ ...RECORD, event: 'timeout' }], {
          token: 'BLK',
          reason: 'timeout',
          park_kind: 'timeout',
        }),
        token: 'BLK',
      }),
    );

    expect(html).toContain('data-signal="needs-you"');
  });
});
