/**
 * `src/lib/runs/queue.ts` (4.16): the QUEUE section's own pure reads — the section-head
 * text, every cell, the parked hint, the request path, and the shared-poll cadence question.
 */
import { describe, expect, it } from 'vitest';

import {
  hasRunningRow,
  isParked,
  nextStepText,
  PARKED_HINT,
  positionText,
  projectCell,
  QUEUE_COLUMNS,
  queueRequestPath,
  queueSectionHeadText,
  REASON_WAITING_ANSWER,
  workflowHref,
  workflowText,
  type QueueItemOut,
  type QueueRun,
} from '../../src/lib/runs/queue';

function run(overrides: Partial<QueueRun> = {}): QueueRun {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    status: 'queued',
    template: 'initiative',
    version: 1,
    project: '22222222-2222-2222-2222-222222222222',
    repository: '33333333-3333-3333-3333-333333333333',
    branch: 'epics/1',
    budget_usd: '15.00',
    spend_usd: '0',
    plan_ref: null,
    created_at: '2026-09-07T09:00:00Z',
    admitted_signals: [],
    ...overrides,
  };
}

function row(overrides: Partial<QueueItemOut> = {}): QueueItemOut {
  return {
    position: 1,
    run: run(),
    next_step_label: 'plan',
    reason: 'repository lock held by initiative v1 · feat/other',
    waiting_since: '2026-09-07T09:00:00Z',
    waiting_seconds: 90,
    ...overrides,
  };
}

describe('QUEUE_COLUMNS', () => {
  it('is the fixed column order the binding rule states', () => {
    expect(QUEUE_COLUMNS).toEqual([
      'pos',
      'project',
      'workflow',
      'next step',
      'waiting because',
      'waiting',
    ]);
  });
});

describe('queueSectionHeadText', () => {
  it('reads the fixed head with the endpoint’s own concurrency figure', () => {
    expect(queueSectionHeadText(2)).toBe(
      'QUEUE · concurrency 2 · one active run per repository · parked runs hold a slot',
    );
  });

  it('never hardcodes the figure — a different payload prints a different number', () => {
    expect(queueSectionHeadText(5)).toContain('concurrency 5');
  });
});

describe('positionText', () => {
  it('prints the position when the engine gives one', () => {
    expect(positionText(1)).toBe('1');
    expect(positionText(2)).toBe('2');
  });

  it('reads an em dash for a Run already holding its slot (AD-12)', () => {
    expect(positionText(null)).toBe('—');
  });
});

describe('workflowText / workflowHref', () => {
  it('reads `{template} v{n} · {branch}`', () => {
    expect(workflowText(run({ template: 'epic', version: 3, branch: 'epics/2' }))).toBe(
      'epic v3 · epics/2',
    );
  });

  it('links to the run detail route', () => {
    expect(workflowHref(run({ id: 'r1' }))).toBe('/workflows/r1');
  });
});

describe('projectCell', () => {
  it('is the Run’s own project id, verbatim — the endpoint carries no name', () => {
    expect(projectCell(run({ project: 'p-1' }))).toBe('p-1');
  });
});

describe('nextStepText', () => {
  it('prints the engine’s own label', () => {
    expect(nextStepText(row({ next_step_label: 'checkout' }))).toBe('checkout');
  });

  it('reads an em dash for a Run with no label yet', () => {
    expect(nextStepText(row({ next_step_label: '' }))).toBe('—');
  });
});

describe('isParked / REASON_WAITING_ANSWER / PARKED_HINT', () => {
  it('is true only for the parked reason', () => {
    expect(isParked(row({ reason: REASON_WAITING_ANSWER }))).toBe(true);
    expect(isParked(row({ reason: 'running' }))).toBe(false);
    expect(isParked(row({ reason: 'global concurrency, held by a, b' }))).toBe(false);
  });

  it('the hint is the fixed literal the binding rule states', () => {
    expect(PARKED_HINT).toBe('not queued until then');
  });
});

describe('queueRequestPath', () => {
  it('is the one path this island always calls, through the proxy', () => {
    expect(queueRequestPath()).toBe('/api/queue');
  });
});

describe('hasRunningRow', () => {
  it('is true when any row reads the running reason', () => {
    expect(
      hasRunningRow([row({ reason: 'running' }), row({ reason: REASON_WAITING_ANSWER })]),
    ).toBe(true);
  });

  it('is false for an empty queue or one with no running row', () => {
    expect(hasRunningRow([])).toBe(false);
    expect(hasRunningRow([row({ reason: REASON_WAITING_ANSWER })])).toBe(false);
  });
});
