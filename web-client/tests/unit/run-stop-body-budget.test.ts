/**
 * `StopBody.tsx`'s budget body (6.6, FR-17, AD-11, UX-DR10): the promoted cost, the numeric
 * field, *Raise budget*, *Cancel run* — and, deliberately, no skips, because AD-13 admits
 * none on this park (`rules/signals.py::VALID`, and `test_signal_rules.py` transcribes it as
 * `budget -> (budget_raise, cancel)`).
 *
 * A new file rather than a case added to `run-stop-body.test.ts`: that one is frozen, and
 * this story's own control renders through a box of its own rather than through the button
 * row those tests read.
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

const PARK_ROW = 'stories[0].build';
const ADMITTED = ['budget_raise', 'cancel'] as SignalKind[];

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

function stopped(admitted: SignalKind[] = ADMITTED, spent = '41.20', budget = '40.00'): string {
  const detail: RunDetailOut = {
    ...base(),
    alert: {
      token: 'BLK',
      reason: `budget $${spent} / $${budget}`,
      park_kind: 'budget',
      payload: {},
    },
    cost: { ...base().cost, spent_usd: spent, budget_usd: budget },
    gate_record: [gate({ event: 'budget', path: PARK_ROW })],
    admitted_signals: admitted,
  } as unknown as RunDetailOut;
  return renderToStaticMarkup(
    createElement(StopBody, {
      detail,
      token: 'BLK' as Token,
      onSignal: () => {},
      onCancelClick: () => {},
      posting: null,
      error: null,
    }),
  );
}

describe('StopBody . budget', () => {
  it('renders the budget stop body at all, which no stop did before this story', () => {
    expect(stopped()).toContain('data-testid="wf-stop-budget"');
  });

  it('shows the reason verbatim, which is the spend against the budget', () => {
    expect(stopped()).toContain('budget $41.20 / $40.00');
  });

  it('promotes the cost into the body', () => {
    const html = stopped();

    expect(html).toContain('data-testid="wf-budget-cost"');
    expect(html).toContain('$41.20 / $40.00');
  });

  it('offers a numeric field pre-filled with a figure that clears the spend', () => {
    const html = stopped();

    expect(html).toContain('data-testid="wf-budget-raise-input"');
    expect(html).toContain('type="number"');
    expect(html).toContain('value="52.00"');
  });

  it('offers Raise budget and Cancel run', () => {
    const html = stopped();

    expect(html).toContain('data-testid="wf-budget-raise"');
    expect(html).toContain('Raise budget');
    expect(html).toContain('data-testid="wf-cancel"');
  });

  it('offers neither skip, because AD-13 admits neither on this park', () => {
    const html = stopped();

    expect(html).not.toContain('data-testid="wf-signal-skip_story"');
    expect(html).not.toContain('data-testid="wf-signal-skip_epic"');
  });

  it('renders no box at all when the server does not admit the raise', () => {
    const html = stopped(['cancel'] as SignalKind[]);

    expect(html).not.toContain('data-testid="wf-budget-raise-input"');
    expect(html).toContain('data-testid="wf-cancel"');
  });

  it('never posts the budget as a plain signal button, which could carry no figure', () => {
    expect(stopped()).not.toContain('data-testid="wf-signal-budget_raise"');
  });
});
