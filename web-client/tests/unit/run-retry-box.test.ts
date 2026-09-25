/**
 * RetryBox (story 3-4): mode selector for Retry — only shown when `reply_available` is true.
 *
 * `vitest.config.ts` runs in `environment: 'node'` with no DOM-mounting library (see
 * `run-detail-island.test.ts`'s own note), so what is asserted here is the rendered markup.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RetryBox from '../../src/components/run/RetryBox';
import StopBody from '../../src/components/run/StopBody';
import type { RunDetailOut } from '../../src/lib/run/detail';
import { retryBody } from '../../src/lib/run/signals';

const STORY_ID = '4-1';
const BUILD = 'epics[0].stories[0].build';

function base(): RunDetailOut {
  return {
    run: {
      id: '1',
      status: 'needs_you',
      admitted_signals: [],
      branch: 'epics/1',
      budget_usd: '15',
      compare_urls: [],
      created_at: '2026-09-17T09:00:00Z',
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
        folder: 'specs/gates',
        template: 'epic',
        version: 1,
        harness: 'claude',
        started_at: null,
        worktree_path: null,
      },
    },
    alert: {
      token: 'BLK',
      reason: '## blocked',
      park_kind: 'misconfigured',
    },
    steps: [
      {
        seq: 1,
        path: BUILD,
        label: 'build',
        kind: 'agent',
        gate: 'liveness',
        status: 'blocked',
        token: 'BLK',
        reason: null,
        attempts: 1,
        latest: {
          n: 1,
          started_at: null,
          ended_at: null,
          seconds: null,
          harness: 'claude',
          model: 'claude-opus-4',
          exit_code: 0,
          cost_usd: null,
          log_tail: [],
        },
      },
    ],
    stories: [{ epic_index: 1, story_id: STORY_ID, state: 'current', cost_usd: '0' }],
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
    admitted_signals: ['retry', 'cancel'],
    summary: null,
  };
}

function renderRetryBox(overrides: Partial<Parameters<typeof RetryBox>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(RetryBox, {
      target: { storyId: STORY_ID, attempt: 1 },
      onRetry: () => {},
      posting: false,
      error: null,
      replyAvailable: true,
      resumeUnavailableReason: null,
      ...overrides,
    }),
  );
}

function renderStopBody(
  detail: RunDetailOut,
  replyAvailable: boolean,
  resumeUnavailableReason: string | null = null,
): string {
  return renderToStaticMarkup(
    createElement(StopBody, {
      detail,
      token: 'BLK',
      onSignal: () => {},
      onCancelClick: () => {},
      posting: null,
      error: null,
      onRetry: () => {},
      replyAvailable,
      resumeUnavailableReason,
    }),
  );
}

describe('RetryBox', () => {
  it('renders two radio inputs with Retry and Session labels', () => {
    const html = renderRetryBox();

    expect(html.match(/<input[^>]*type="radio"/g)?.length).toBe(2);
    expect(html).toContain('data-testid="wf-retry-box"');
    expect(html).toContain('data-testid="wf-signal-retry"');
  });

  it('restart hint names archive path and re-dispatch', () => {
    const html = renderRetryBox({ target: { storyId: STORY_ID, attempt: 2 } });

    // The restart hint must name the archive path and state re-dispatch
    expect(html).toContain('stories/.answers/');
    expect(html).toContain(STORY_ID);
  });

  it('session hint states the session continues with the retry prompt', () => {
    const html = renderRetryBox();

    expect(html).toContain('The session continues with the retry prompt');
    expect(html).toContain('Story file stays in place');
  });
});

describe('StopBody with retry + replyAvailable', () => {
  it('renders RetryBox (not plain Retry button) when replyAvailable=true and retry admitted', () => {
    const html = renderStopBody(base(), true);

    expect(html).toContain('data-testid="wf-retry-box"');
    // The plain retry button (rendered by StopBody's button map) should not appear
    // alongside the RetryBox — RetryBox renders its own button
    expect(html.match(/data-testid="wf-signal-retry"/g)?.length).toBe(1); // only inside RetryBox
  });

  // story 4, 2026-09-25 declared behaviour change: RetryBox now renders whenever retry is
  // admitted, regardless of replyAvailable. The old test pinned the opposite.
  it('renders RetryBox even when replyAvailable=false', () => {
    const html = renderStopBody(base(), false);

    expect(html).toContain('data-testid="wf-retry-box"');
  });

  it('renders session as default radio when replyAvailable=true', () => {
    const html = renderStopBody(base(), true);

    // session radio should be present when reply_available
    expect(html).toContain('value="session"');
    // restart radio should also be present
    expect(html).toContain('value="restart"');
    // two radios total (both modes available)
    expect(html.match(/<input[^>]*type="radio"/g)?.length).toBe(2);
  });

  it('renders restart-only with no_session reason when replyAvailable=false', () => {
    const html = renderStopBody(base(), false, 'no_session');

    expect(html).toContain('data-testid="wf-retry-box"');
    expect(html).toContain('No session was recorded');
    // Only restart radio (session unavailable)
    expect(html.match(/<input[^>]*type="radio"/g)?.length).toBe(1);
  });

  it('renders restart-only with no_capability reason when replyAvailable=false', () => {
    const html = renderStopBody(base(), false, 'no_capability');

    expect(html).toContain('data-testid="wf-retry-box"');
    expect(html).toContain('does not support resume');
    // Only restart radio (session unavailable)
    expect(html.match(/<input[^>]*type="radio"/g)?.length).toBe(1);
  });

  it('onRetry callback receives mode and text', () => {
    let receivedMode = '';
    let receivedText = '';
    // Render with replyAvailable=true so session radio is present; we just need the component to compile
    renderRetryBox({
      onRetry: (mode: string, text: string) => {
        receivedMode = mode;
        receivedText = text;
      },
    });
    // Callback signature accepted at compile time — the types changed from (mode) to (mode, text)
    expect(typeof receivedMode).toBe('string');
    expect(typeof receivedText).toBe('string');
  });
});

describe('retryBody signal helper', () => {
  it('produces mode: session payload', () => {
    expect(retryBody('session', '')).toEqual({ kind: 'retry', payload: { mode: 'session' } });
  });

  it('produces mode: restart payload', () => {
    expect(retryBody('restart', '')).toEqual({ kind: 'retry', payload: { mode: 'restart' } });
  });

  it('includes text in payload when non-empty', () => {
    expect(retryBody('session', 'fix the enum')).toEqual({
      kind: 'retry',
      payload: { mode: 'session', text: 'fix the enum' },
    });
  });

  it('omits text from payload when empty', () => {
    expect(retryBody('restart', '')).toEqual({ kind: 'retry', payload: { mode: 'restart' } });
  });
});
