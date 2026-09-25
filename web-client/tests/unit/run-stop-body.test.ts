/**
 * `StopBody.tsx` (4.15, UX-DR10): the story's own acceptance criteria, rendered directly —
 * `plan_stale`'s exact button pair, `push_rejected`'s resolve line and log tail, the `failed`
 * body's log tail with no signal button at all but the `start a new run` link.
 *
 * Stateless (`renderToStaticMarkup`); the click handlers are proven end to end in
 * `tests/e2e/run-detail.spec.ts`, a real browser.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import StopBody from '../../src/components/run/StopBody';
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
    alert: { token: 'BLK', reason: 'plan stale: stories.yaml', park_kind: 'plan_stale' },
    steps: [
      {
        seq: 1,
        path: 'plan',
        label: 'plan',
        kind: 'plan.check',
        gate: 'deterministic',
        status: 'error',
        token: 'ERR',
        reason: 'plan stale: stories.yaml',
        attempts: 1,
        latest: null,
      },
    ],
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
    gate_record: [
      {
        id: 'g1',
        at: '2026-09-07T09:05:00Z',
        path: 'plan',
        event: 'plan_stale',
        actor: 'machine',
        text: 'plan stale: stories.yaml',
        attempt_n: null,
      },
    ],
    admitted_signals: ['continue', 'cancel'],
    summary: null,
  };
}

function render(detail: RunDetailOut, token: Parameters<typeof StopBody>[0]['token']): string {
  return renderToStaticMarkup(
    createElement(StopBody, {
      detail,
      token,
      onSignal: () => {},
      onCancelClick: () => {},
      posting: null,
      error: null,
    }),
  );
}

describe('StopBody · plan_stale', () => {
  it('shows the reason, no diff endpoint, and exactly Continue and Cancel run', () => {
    const html = render(base(), 'BLK');

    expect(html).toContain('data-testid="wf-stop-plan_stale"');
    expect(html).toContain('plan stale: stories.yaml');
    expect(html).toContain('data-testid="wf-signal-continue"');
    expect(html).toContain('Continue');
    expect(html).toContain('data-testid="wf-cancel"');
    expect(html).toContain('Cancel run');
    expect(html).not.toContain('data-testid="wf-signal-retry"');
    expect(html).toContain('start a new run');
  });
});

describe('StopBody · push_rejected', () => {
  it('shows the log tail and the resolve line; Retry is offered when admitted', () => {
    const detail: RunDetailOut = {
      ...base(),
      alert: {
        token: 'BLK',
        reason: 'push rejected: non-fast-forward',
        park_kind: 'push_rejected',
      },
      steps: [
        {
          seq: 2,
          path: 'push',
          label: 'push',
          kind: 'git.push',
          gate: 'deterministic',
          status: 'error',
          token: 'ERR',
          reason: 'push rejected',
          attempts: 1,
          latest: {
            n: 1,
            started_at: null,
            ended_at: null,
            seconds: null,
            harness: null,
            model: null,
            exit_code: 1,
            cost_usd: null,
            log_tail: ['! [rejected]  main -> main'],
          },
        },
      ],
      gate_record: [
        {
          id: 'g1',
          at: '2026-09-07T09:05:00Z',
          path: 'push',
          event: 'push_rejected',
          actor: 'machine',
          text: 'push rejected',
          attempt_n: null,
        },
      ],
      admitted_signals: ['retry', 'cancel'],
    };
    const html = render(detail, 'BLK');

    expect(html).toContain('data-testid="wf-stop-push_rejected"');
    expect(html).toContain('resolve on the remote, then Retry');
    expect(html).toContain('[rejected]');
    expect(html).toContain('data-testid="wf-signal-retry"');
    expect(html).toContain('data-testid="wf-cancel"');
  });
});

describe('StopBody · checkpoint', () => {
  it('shows the story summary and offers Continue', () => {
    const detail: RunDetailOut = {
      ...base(),
      alert: { token: 'CHK', reason: 'story checkpoint', park_kind: 'checkpoint' },
      gate_record: [
        {
          id: 'g1',
          at: '2026-09-07T09:05:00Z',
          path: 'checkpoint-row',
          event: 'checkpoint',
          actor: 'machine',
          text: 'story checkpoint',
          attempt_n: null,
        },
      ],
    };
    const html = render(detail, 'CHK');

    expect(html).toContain('data-testid="wf-stop-checkpoint"');
    expect(html).toContain('story checkpoint');
    expect(html).toContain('data-testid="wf-signal-continue"');
  });
});

describe('StopBody · failed', () => {
  it('shows the log tail and only the start-a-new-run link, no signal buttons', () => {
    const detail: RunDetailOut = {
      ...base(),
      run: { ...base().run, status: 'failed' },
      alert: null,
      steps: [
        {
          seq: 1,
          path: 'build',
          label: 'build',
          kind: 'shell',
          gate: 'deterministic',
          status: 'error',
          token: 'ERR',
          reason: 'exit 1',
          attempts: 1,
          latest: {
            n: 1,
            started_at: null,
            ended_at: null,
            seconds: null,
            harness: null,
            model: null,
            exit_code: 1,
            cost_usd: null,
            log_tail: ['npm ERR!'],
          },
        },
      ],
      gate_record: [
        {
          id: 'g1',
          at: '2026-09-07T09:05:00Z',
          path: 'build',
          event: 'failed',
          actor: 'machine',
          text: 'exit 1',
          attempt_n: null,
        },
      ],
      admitted_signals: [],
    };
    const html = render(detail, 'ERR');

    expect(html).toContain('data-testid="wf-stop-failed"');
    expect(html).toContain('npm ERR!');
    expect(html).toContain('start a new run');
    expect(html).not.toContain('data-testid="wf-signal-retry"');
    expect(html).not.toContain('data-testid="wf-cancel"');
  });
});

describe('StopBody · other states', () => {
  // story 2, 2026-09-25 declared behaviour change: running/queued now render cancel when
  // admitted; this test pins the no-cancel path (admitted_signals: [] for all four cases).
  it('renders nothing when cancel is not admitted (running, done, cancelled, queued)', () => {
    for (const [status, token] of [
      ['running', 'RUN'],
      ['done', 'DON'],
      ['cancelled', 'CAN'],
      ['queued', 'QUE'],
    ] as const) {
      const detail: RunDetailOut = {
        ...base(),
        run: { ...base().run, status, admitted_signals: [] },
        alert: null,
        admitted_signals: [],
      };
      expect(render(detail, token)).toBe('');
    }
  });
});

describe('StopBody · a 409 refusal', () => {
  it('prints the problem detail beside the buttons', () => {
    const html = renderToStaticMarkup(
      createElement(StopBody, {
        detail: base(),
        token: 'BLK',
        onSignal: () => {},
        onCancelClick: () => {},
        posting: null,
        error: {
          status: 409,
          title: 'conflict',
          type: 'about:blank',
          detail: 'continue not available yet',
        },
      }),
    );

    expect(html).toContain('data-testid="wf-signal-error"');
    expect(html).toContain('continue not available yet');
  });
});
