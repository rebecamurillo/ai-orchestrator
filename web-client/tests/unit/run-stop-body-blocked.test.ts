/**
 * `StopBody.tsx`'s 5.10 additions — the `blocked` Question block and the `misconfigured`
 * body (UX-DR9, UX-DR10) — kept apart from the frozen `run-stop-body.test.ts`, which
 * predates both `park_kind`s entirely.
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
    gate_record: [],
    admitted_signals: [],
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

describe('StopBody · blocked', () => {
  it('shows the whole question and exactly the admitted skip/cancel buttons', () => {
    const detail: RunDetailOut = {
      ...base(),
      alert: {
        token: 'BLK',
        reason: '## Auto Run Result\n\nWhich database should this use?\n\nA follow-up paragraph.',
        park_kind: 'blocked',
        attribution: {
          harness: 'claude',
          model: 'claude-opus-4',
          ended_at: '2026-09-07T09:05:00Z',
        },
      },
      admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'],
    };

    const html = render(detail, 'BLK');

    expect(html).toContain('data-testid="wf-stop-blocked"');
    expect(html).toContain('data-testid="wf-question"');
    expect(html).toContain('Agent · claude · claude-opus-4 · 2026-09-07T09:05:00Z');
    expect(html).toContain('Which database should this use?');
    expect(html).toContain('A follow-up paragraph.');
    expect(html).toContain('data-testid="wf-signal-skip_story"');
    expect(html).toContain('Skip story');
    expect(html).toContain('data-testid="wf-signal-skip_epic"');
    expect(html).toContain('Skip epic');
    expect(html).toContain('data-testid="wf-cancel"');
    expect(html).not.toContain('data-testid="wf-signal-answer"');
    expect(html).not.toContain('<textarea');
  });
});

describe('StopBody · misconfigured', () => {
  it('shows the condition and the log tail, and contains no textarea', () => {
    const detail: RunDetailOut = {
      ...base(),
      alert: { token: 'BLK', reason: 'no story file', park_kind: 'misconfigured' },
      steps: [
        {
          seq: 1,
          path: 'stories[0].build',
          label: 'build',
          kind: 'agent',
          gate: 'liveness',
          status: 'error',
          token: 'ERR',
          reason: 'no story file',
          attempts: 1,
          latest: {
            n: 1,
            started_at: null,
            ended_at: null,
            seconds: null,
            harness: 'claude',
            model: 'claude-opus-4',
            exit_code: 1,
            cost_usd: null,
            log_tail: ['reading stories/1-*.md', 'no match'],
          },
        },
      ],
      gate_record: [
        {
          id: 'g1',
          at: '2026-09-07T09:05:00Z',
          path: 'stories[0].build',
          event: 'misconfigured',
          actor: 'machine',
          text: 'no story file',
          attempt_n: null,
        },
      ],
      admitted_signals: ['retry', 'skip_story', 'skip_epic', 'cancel'],
    };

    const html = render(detail, 'BLK');

    expect(html).toContain('data-testid="wf-stop-misconfigured"');
    expect(html).toContain('no story file');
    expect(html).toContain('no match');
    expect(html).toContain('data-testid="wf-signal-retry"');
    expect(html).toContain('data-testid="wf-signal-skip_story"');
    expect(html).toContain('data-testid="wf-cancel"');
    expect(html).not.toContain('<textarea');
    expect(html).not.toContain('data-testid="wf-signal-continue"');
  });

  it('shows the file list when the condition names files', () => {
    const detail: RunDetailOut = {
      ...base(),
      alert: {
        token: 'BLK',
        reason: 'ambiguous story file: 1-a.md, 1-b.md',
        park_kind: 'misconfigured',
      },
      admitted_signals: ['retry', 'cancel'],
    };

    const html = render(detail, 'BLK');

    expect(html).toContain('data-testid="wf-stop-files"');
    expect(html).toContain('1-a.md');
    expect(html).toContain('1-b.md');
  });

  it('omits the file list when the condition names none', () => {
    const detail: RunDetailOut = {
      ...base(),
      alert: {
        token: 'BLK',
        reason: 'harness misconfigured: no subagents',
        park_kind: 'misconfigured',
      },
      admitted_signals: ['retry', 'cancel'],
    };

    const html = render(detail, 'BLK');

    expect(html).not.toContain('data-testid="wf-stop-files"');
  });
});
