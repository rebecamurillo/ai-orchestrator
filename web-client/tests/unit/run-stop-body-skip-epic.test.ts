/**
 * `StopBody.tsx`'s *Skip epic* control (6.5, FR-20) — the five stops that had no such button
 * before this story (`verify_failed`, `timeout`, `protected_path`, `internal`,
 * `push_rejected`), the three that already rendered it as a plain button
 * (`blocked`/`misconfigured`/`checkpoint`, 5.10/6.2, now a confirm instead), and the
 * `push_rejected` variant of the confirm sentence.
 *
 * Kept apart from `run-stop-body-skip.test.ts` (6.4, *Skip story*) and from
 * `run-stop-body.test.ts`/`-blocked.test.ts`/`-checkpoint.test.ts`/`-answer.test.ts`, which
 * are frozen and assert only that the `wf-signal-skip_epic` trigger is present — which the
 * confirm's closed render still is (`ConfirmAction`'s own doc, 6.4).
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import StopBody from '../../src/components/run/StopBody';
import type {
  GateRecordOut,
  RunDetailOut,
  SignalKind,
  StepRowOut,
  Token,
} from '../../src/lib/run/detail';

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

function gate(over: Partial<GateRecordOut> = {}): GateRecordOut {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    at: '2026-09-09T10:00:00Z',
    path: null,
    event: 'blocked',
    actor: 'machine',
    text: '',
    attempt_n: null,
    ...over,
  };
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
        folder: 'specs/gates',
        template: 'initiative',
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

function stopped(
  parkKind: string,
  admitted: SignalKind[],
  path = 'epics[0].push',
  token: Token = 'BLK',
): string {
  const detail: RunDetailOut = {
    ...base(),
    alert: { token, reason: 'why it stopped', park_kind: parkKind },
    gate_record: [gate({ event: parkKind as GateRecordOut['event'], path })],
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

const WITH_SKIP_EPIC: SignalKind[] = ['retry', 'skip_epic', 'cancel'];

describe('StopBody · Skip epic', () => {
  it.each(['verify_failed', 'timeout', 'protected_path', 'internal'])(
    'offers it on a %s stop, which had no such button before',
    (parkKind) => {
      const html = stopped(parkKind, WITH_SKIP_EPIC);

      expect(html).toContain('data-testid="wf-signal-skip_epic"');
      expect(html).toContain('Skip epic');
    },
  );

  it('offers it on a push_rejected stop, unlike Skip story', () => {
    const html = stopped('push_rejected', WITH_SKIP_EPIC);

    expect(html).toContain('data-testid="wf-signal-skip_epic"');
  });

  it('renders it exactly once on a stop whose own filter already lists it', () => {
    const html = stopped('blocked', ['answer', 'skip_epic', 'cancel']);

    expect(html.split('data-testid="wf-signal-skip_epic"')).toHaveLength(2);
  });

  it('keeps the buttons that stop already had', () => {
    const html = stopped('verify_failed', WITH_SKIP_EPIC);

    expect(html).toContain('data-testid="wf-signal-retry"');
    expect(html).toContain('data-testid="wf-cancel"');
  });

  it('shows no confirm line until the trigger is clicked', () => {
    const html = stopped('verify_failed', WITH_SKIP_EPIC);

    expect(html).not.toContain('data-testid="wf-confirm-skip_epic"');
    expect(html).not.toContain('remaining stories are marked skipped');
  });

  it('appends nothing on a Template that can carry no epic frame', () => {
    // `offersSkipEpic`'s template check only governs the *appending* this story does on the
    // five stops `blockedSignals`/`checkpointSignals` do not reach: those two filters
    // already render `skip_epic` unconditionally whenever `admitted_signals` carries it
    // (5.10/6.2, frozen), the same pre-existing gap 6.4's own hand-back names for
    // `skip_story` on a park outside every Story frame — not this story's to close.
    const detail: RunDetailOut = {
      ...base(),
      run: { ...base().run, template: 'repo-init' },
      alert: { token: 'BLK', reason: 'why it stopped', park_kind: 'verify_failed' },
      gate_record: [],
      admitted_signals: WITH_SKIP_EPIC,
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

    expect(html).not.toContain('data-testid="wf-signal-skip_epic"');
  });

  it('offers nothing where the server did not admit it', () => {
    const html = stopped('verify_failed', ['retry', 'cancel']);

    expect(html).not.toContain('data-testid="wf-signal-skip_epic"');
  });
});
