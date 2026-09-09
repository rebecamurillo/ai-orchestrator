/**
 * `StopBody.tsx`'s *Skip story* control (6.4, FR-20) — the four stops that had no such
 * button before this story, and the three that did.
 *
 * `verify_failed`, `timeout`, `protected_path` and `internal` all render through
 * `detail.ts::stopSignals`, whose `EFFECTIVE_KINDS` is frozen to `cancel`/`retry`/`continue`
 * by `run-detail-lib.test.ts` — so the control is appended by `lib/run/skip.ts::
 * offersSkipStory` rather than by widening that filter, and this module is what proves the
 * appending works on all seven bodies without disturbing the buttons already there.
 *
 * Kept apart from `run-stop-body.test.ts`/`run-stop-body-blocked.test.ts`/
 * `-checkpoint.test.ts`/`-answer.test.ts`, which are frozen and assert only that the
 * `wf-signal-skip_story` trigger is present — which the confirm's closed render still is.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import StopBody from '../../src/components/run/StopBody';
import type { RunDetailOut, SignalKind, StepRowOut, Token } from '../../src/lib/run/detail';

const PARK_ROW = 'stories[1].verify';

function step(over: Partial<StepRowOut> = {}): StepRowOut {
  return {
    seq: 1,
    path: PARK_ROW,
    label: 'verify',
    kind: 'shell',
    gate: 'deterministic',
    status: 'error',
    token: 'ERR',
    reason: 'exit 1',
    attempts: 1,
    latest: null,
    cost_usd: '0',
    ...over,
  } as StepRowOut;
}

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
    steps: [step()],
    stories: [{ epic_index: 0, story_id: '2', state: 'current', cost_usd: '0' }],
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
  } as unknown as RunDetailOut;
}

function stopped(parkKind: string, admitted: SignalKind[], token: Token = 'BLK'): string {
  const detail: RunDetailOut = {
    ...base(),
    alert: { token, reason: 'why it stopped', park_kind: parkKind },
    admitted_signals: admitted,
  } as unknown as RunDetailOut;
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

const WITH_SKIP: SignalKind[] = ['retry', 'skip_story', 'skip_epic', 'cancel'];

describe('StopBody · Skip story', () => {
  it.each(['verify_failed', 'timeout', 'protected_path', 'internal'])(
    'offers it on a %s stop, which had no such button before',
    (parkKind) => {
      const html = stopped(parkKind, WITH_SKIP);

      expect(html).toContain('data-testid="wf-signal-skip_story"');
      expect(html).toContain('Skip story');
    },
  );

  it('keeps the buttons that stop already had', () => {
    const html = stopped('verify_failed', WITH_SKIP);

    expect(html).toContain('data-testid="wf-signal-retry"');
    expect(html).toContain('data-testid="wf-cancel"');
  });

  it('renders it exactly once on a stop whose own filter already lists it', () => {
    const html = stopped('blocked', ['answer', 'skip_story', 'skip_epic', 'cancel']);

    expect(html.split('data-testid="wf-signal-skip_story"')).toHaveLength(2);
  });

  it('shows nothing after the re-baseline park, where the server withdrew it', () => {
    const html = stopped('verify_failed', ['retry', 'skip_epic', 'cancel']);

    expect(html).not.toContain('data-testid="wf-signal-skip_story"');
    expect(html).toContain('data-testid="wf-signal-retry"');
  });

  it('shows no confirm line until the trigger is clicked', () => {
    const html = stopped('verify_failed', WITH_SKIP);

    expect(html).not.toContain('data-testid="wf-confirm-skip_story"');
    expect(html).not.toContain('its remaining steps are marked skipped');
  });

  it('offers nothing on a push_rejected stop, which AD-13 refuses the kind on', () => {
    const html = stopped('push_rejected', ['retry', 'skip_epic', 'cancel']);

    expect(html).not.toContain('data-testid="wf-signal-skip_story"');
  });

  it('offers nothing when the response names no Story to skip', () => {
    // an `internal` park on a row outside every story frame: `admitted_signals` answers from
    // the park kind alone and still lists the kind, but `validate` would refuse it (409) and
    // the confirm could name no id — see `lib/run/skip.ts::offersSkipStory`
    const detail = {
      ...base(),
      stories: [],
      alert: { token: 'BLK', reason: 'internal: KeyError', park_kind: 'internal' },
      admitted_signals: WITH_SKIP,
    } as unknown as RunDetailOut;
    const html = renderToStaticMarkup(
      createElement(StopBody, {
        detail,
        token: 'BLK' as Token,
        onSignal: () => {},
        onCancelClick: () => {},
        posting: null,
        error: null,
      }),
    );

    expect(html).not.toContain('data-testid="wf-signal-skip_story"');
    expect(html).toContain('data-testid="wf-signal-retry"');
  });
});
