/**
 * `GateRecord.tsx` (4.15): `time · path · event · actor · text`, oldest first, the last row
 * marked `■` in the signal colour while the Run is stopped (`renderToStaticMarkup`,
 * stateless).
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import GateRecord from '../../src/components/run/GateRecord';
import type { GateRecordOut, RunDetailOut } from '../../src/lib/run/detail';

function detail(records: GateRecordOut[]): RunDetailOut {
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
    alert: null,
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

describe('GateRecord', () => {
  it('lists every field for every record', () => {
    const html = renderToStaticMarkup(
      createElement(GateRecord, {
        detail: detail([
          {
            id: 'g1',
            at: '2026-09-07T09:00:00Z',
            path: 'plan',
            event: 'start',
            actor: 'machine',
            text: 'plan started',
            attempt_n: null,
          },
          {
            id: 'g2',
            at: '2026-09-07T09:05:00Z',
            path: 'plan',
            event: 'plan_stale',
            actor: 'machine',
            text: 'plan stale: stories.yaml',
            attempt_n: null,
          },
        ]),
        token: 'BLK',
      }),
    );

    expect(html).toContain('data-testid="wf-gate-record"');
    expect(html).toContain('plan started');
    expect(html).toContain('plan stale: stories.yaml');
  });

  it('marks the last row ■ in the signal colour while stopped', () => {
    const html = renderToStaticMarkup(
      createElement(GateRecord, {
        detail: detail([
          {
            id: 'g1',
            at: '2026-09-07T09:05:00Z',
            path: 'plan',
            event: 'plan_stale',
            actor: 'machine',
            text: 'plan stale',
            attempt_n: null,
          },
        ]),
        token: 'BLK',
      }),
    );

    expect(html).toContain('data-signal="needs-you"');
  });

  it('carries no signal colour on the last row for a running Run', () => {
    const html = renderToStaticMarkup(
      createElement(GateRecord, {
        detail: detail([
          {
            id: 'g1',
            at: '2026-09-07T09:00:00Z',
            path: 'plan',
            event: 'start',
            actor: 'machine',
            text: 'started',
            attempt_n: null,
          },
        ]),
        token: 'RUN',
      }),
    );

    expect(html).not.toContain('data-signal');
  });
});
