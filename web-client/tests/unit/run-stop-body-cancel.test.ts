/**
 * `StopBody.tsx` non-stop cancel path (story 2, 2026-09-25): when a Run is `running` or
 * `queued` and `admitted_signals` includes `cancel`, `StopBody` renders a Cancel button
 * without any stop-body wrapper. When cancel is not admitted, it renders nothing.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import StopBody from '../../src/components/run/StopBody';
import type { RunDetailOut } from '../../src/lib/run/detail';

function makeDetail(status: 'running' | 'queued', signals: string[]): RunDetailOut {
  return {
    run: {
      id: '1',
      status,
      admitted_signals: signals as RunDetailOut['admitted_signals'],
      branch: 'feat/step-handling-1',
      budget_usd: '15',
      compare_urls: [],
      created_at: '2026-09-25T10:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: 'p1',
      repository: 'r1',
      spend_usd: '0',
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
        folder: 'docs',
        template: 'epic',
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
    admitted_signals: signals as RunDetailOut['admitted_signals'],
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

describe('StopBody · non-stop cancel path', () => {
  it('cancel button renders when running and cancel admitted', () => {
    const html = render(makeDetail('running', ['cancel']), 'RUN');

    expect(html).toContain('data-testid="wf-cancel"');
    expect(html).toContain('Cancel run');
    expect(html).not.toMatch(/data-testid="wf-stop-/);
  });

  it('cancel button renders when queued and cancel admitted', () => {
    const html = render(makeDetail('queued', ['cancel']), 'QUE');

    expect(html).toContain('data-testid="wf-cancel"');
    expect(html).toContain('Cancel run');
    expect(html).not.toMatch(/data-testid="wf-stop-/);
  });

  it('nothing renders when running without cancel', () => {
    const html = render(makeDetail('running', []), 'RUN');

    expect(html).toBe('');
  });
});
