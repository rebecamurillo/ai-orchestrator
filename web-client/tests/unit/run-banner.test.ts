/**
 * `Banner.tsx` (4.15, UX-DR9): the Alert banner, the `done` summary, the `cancelled` line,
 * and nothing at all for `running`/`queued`. Stateless (`renderToStaticMarkup`).
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
      admitted_signals: ['continue', 'cancel'],
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
    alert: { token: 'BLK', reason: 'plan stale: stories.yaml', park_kind: 'plan_stale' },
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
    admitted_signals: ['continue', 'cancel'],
    summary: null,
  };
}

function render(detail: RunDetailOut, token: Parameters<typeof Banner>[0]['token']): string {
  return renderToStaticMarkup(createElement(Banner, { detail, token }));
}

describe('Banner', () => {
  it('shows the reason verbatim and spent/budget for a parked Run', () => {
    const html = render(base(), 'BLK');

    expect(html).toContain('data-testid="wf-alert"');
    expect(html).toContain('data-signal="needs-you"');
    expect(html).toContain('plan stale: stories.yaml');
    expect(html).toContain('$4.18 / $15.00');
  });

  it('is red for a failed Run', () => {
    const detail = { ...base(), run: { ...base().run, status: 'failed' as const }, alert: null };
    const html = render(detail, 'ERR');

    expect(html).toContain('data-signal="failed"');
  });

  it('replaces the banner with the done summary line, no alert', () => {
    const detail = {
      ...base(),
      run: { ...base().run, status: 'done' as const },
      alert: null,
      summary: { progress: null, links: ['https://a'], skipped: ['4-9'] },
    };
    const html = render(detail, 'DON');

    expect(html).toContain('data-testid="wf-summary"');
    expect(html).toContain('1 link · skipped: 4-9');
    expect(html).not.toContain('data-testid="wf-alert"');
  });

  it('reads cancelled by operator at {time} for a cancelled Run', () => {
    const detail = {
      ...base(),
      run: { ...base().run, status: 'cancelled' as const },
      alert: null,
      gate_record: [
        {
          id: 'g1',
          at: '2026-09-07T11:00:00Z',
          path: null,
          event: 'cancel' as const,
          actor: 'operator' as const,
          text: 'cancelled by the operator',
          attempt_n: null,
        },
      ],
    };
    const html = render(detail, 'CAN');

    expect(html).toContain('cancelled by operator at 2026-09-07T11:00:00Z');
  });

  it('renders nothing while running or queued', () => {
    const running = { ...base(), run: { ...base().run, status: 'running' as const }, alert: null };
    const queued = { ...base(), run: { ...base().run, status: 'queued' as const }, alert: null };

    expect(render(running, 'RUN')).toBe('');
    expect(render(queued, 'QUE')).toBe('');
  });
});
