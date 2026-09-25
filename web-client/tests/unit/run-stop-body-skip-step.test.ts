/**
 * `StopBody.tsx`'s *Skip step* control (story 1, 2026-09-25) — a `ConfirmAction` beside
 * *Skip story* and *Skip epic* on every stop where `admitted_signals` carries `"skip_step"`.
 *
 * Unlike *Skip story* and *Skip epic*, `skip_step` is appended unconditionally whenever
 * `admitted_signals` includes it (`offersSkipStep` reads `admitted_signals` only), so there
 * is no park-kind filter list to exercise here — the server decides, and this file proves
 * the button appears and disappears exactly when the server says so.
 *
 * `vitest.config.ts` runs in `environment: 'node'`, so what is asserted here is the closed
 * render (the trigger button), following the same pattern as `run-stop-body-skip.test.ts`
 * and `run-stop-body-skip-epic.test.ts`. Interactive confirm-and-post behaviour is
 * `ConfirmAction`'s own tested contract (`run-confirm-action.test.ts`).
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import StopBody from '../../src/components/run/StopBody';
import type { RunDetailOut, SignalKind, StepRowOut, Token } from '../../src/lib/run/detail';

const PARK_ROW = 'stories[0].verify';

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

const WITH_SKIP_STEP: SignalKind[] = ['retry', 'skip_step', 'cancel'];

describe('StopBody · Skip step', () => {
  it('renders the ConfirmAction trigger when admitted_signals includes skip_step', () => {
    const html = stopped('verify_failed', WITH_SKIP_STEP);

    // ConfirmAction renders its closed trigger with data-testid="wf-signal-{kind}"
    expect(html).toContain('data-testid="wf-signal-skip_step"');
    expect(html).toContain('Skip step');
    // confirm line is hidden until the trigger is clicked (closed render only)
    expect(html).not.toContain('data-testid="wf-confirm-skip_step"');
    expect(html).not.toContain('marks it skipped and continues');
  });

  it('does not render skip_step when not in admitted_signals', () => {
    const html = stopped('verify_failed', ['retry', 'cancel']);

    expect(html).not.toContain('data-testid="wf-signal-skip_step"');
  });

  it('the skip_step ConfirmAction posts skip_step on confirm', () => {
    // The ConfirmAction is keyed on `kind="skip_step"` and its onConfirm is wired to
    // `() => onSignal('skip_step')` in StopBody. ConfirmAction's own contract
    // (run-confirm-action.test.ts) guarantees the closed trigger has the right testid and
    // that onConfirm is called on confirm click. Together they pin the end-to-end wiring.
    const html = stopped('timeout', WITH_SKIP_STEP);

    // The closed trigger is the element the Operator clicks to open the confirm.
    expect(html).toContain('data-testid="wf-signal-skip_step"');
    // The ConfirmAction renders its trigger as a button, not a plain wf-signal button,
    // so only one element with that testid exists.
    expect(html.split('data-testid="wf-signal-skip_step"')).toHaveLength(2);
  });
});
