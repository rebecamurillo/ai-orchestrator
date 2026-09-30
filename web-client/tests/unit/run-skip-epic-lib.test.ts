/**
 * `src/lib/run/skip.ts`'s 6.5 additions: which stops offer *Skip epic*, the epic number the
 * confirm line names, and the confirm sentence itself (including its `push_rejected`
 * variant). Kept apart from `run-skip-lib.test.ts` (6.4): `offersSkipEpic` is deliberately
 * not symmetric with `offersSkipStory` — see `src/lib/run/skip.ts`'s own module doc.
 */
import { describe, expect, it } from 'vitest';

import type { GateRecordOut, RunDetailOut, SignalKind } from '../../src/lib/run/detail';
import {
  SKIP_EPIC_LABEL,
  SKIP_EPIC_STOP_KINDS,
  currentEpicNumber,
  offersSkipEpic,
  skipEpicConfirmLine,
} from '../../src/lib/run/skip';

const ADMITTED: SignalKind[] = ['retry', 'skip_epic', 'cancel'];

function gate(overrides: Partial<GateRecordOut> = {}): GateRecordOut {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    at: '2026-09-09T10:00:00Z',
    path: null,
    event: 'start',
    actor: 'machine',
    text: '',
    attempt_n: null,
    ...overrides,
  };
}

function parkedAt(
  path: string | null,
  parkKind: string,
  template = 'initiative',
  gateRecordEvent = parkKind,
): RunDetailOut {
  return {
    run: { status: path === null ? 'queued' : 'needs_you', template },
    alert: path === null ? null : { token: 'BLK', reason: '', park_kind: parkKind },
    gate_record:
      path === null ? [] : [gate({ event: gateRecordEvent as GateRecordOut['event'], path })],
  } as unknown as RunDetailOut;
}

describe('offersSkipEpic', () => {
  it('offers the action on all eight bodies AD-13 admits it on, over either frame shape', () => {
    expect([...SKIP_EPIC_STOP_KINDS]).toEqual([
      'blocked',
      'checkpoint',
      'verify_failed',
      'timeout',
      'push_rejected',
      'protected_path',
      'misconfigured',
      'internal',
    ]);
    // Operator decision 2026-09-30: no template name hardcoded in product code. The server
    // ran `_has_epic_frame` over the Run's rows before it sent `admitted_signals`, so both
    // of its branches are already decided; the Template's name says nothing on either side.
    for (const kind of SKIP_EPIC_STOP_KINDS) {
      expect(offersSkipEpic(parkedAt('push', kind, 'house-epic'), kind, ADMITTED)).toBe(true);
      expect(offersSkipEpic(parkedAt('epics[0].push', kind, 'renamed-copy'), kind, ADMITTED)).toBe(
        true,
      );
    }
  });

  it('never offers it where the server did not admit it', () => {
    const d = parkedAt('push', 'blocked', 'epic');
    expect(offersSkipEpic(d, 'blocked', ['retry', 'cancel'])).toBe(false);
  });

  it('never offers it on a body outside the list, or on no stop at all', () => {
    const epic = (kind: string) => parkedAt('push', kind, 'epic');
    expect(offersSkipEpic(epic('plan_stale'), 'plan_stale', ADMITTED)).toBe(false);
    expect(offersSkipEpic(epic('budget'), 'budget', ADMITTED)).toBe(false);
    expect(offersSkipEpic(epic('failed'), 'failed', ADMITTED)).toBe(false);
    expect(offersSkipEpic(epic('blocked'), null, ADMITTED)).toBe(false);
  });

  it('never offers it when the server left the kind out, whatever the path looks like', () => {
    // The refusal `_has_epic_frame` makes now arrives as an absent `skip_epic`: the server
    // reads the Run's own rows for it (Operator decision 2026-09-30), and this side does not
    // guess a second time off the Template's name or the parked path.
    const d = parkedAt('stories[0].build', 'blocked', 'house-initiative');
    expect(offersSkipEpic(d, 'blocked', ['retry', 'cancel'])).toBe(false);
    expect(offersSkipEpic(d, 'blocked', ADMITTED)).toBe(true);
  });
});

describe('currentEpicNumber', () => {
  it('reads the 1-based number off the parked rows own epics[n] bracket', () => {
    const d = parkedAt('epics[0].stories[1].build', 'blocked');
    expect(currentEpicNumber(d)).toBe(1);

    const second = parkedAt('epics[2].push', 'push_rejected');
    expect(currentEpicNumber(second)).toBe(3);
  });

  it('is 1 for a Run that is itself one epic: no bracket at all', () => {
    const d = parkedAt('push', 'push_rejected', 'house-epic');
    expect(currentEpicNumber(d)).toBe(1);
  });

  it('is 1 when no current row path is known yet', () => {
    expect(currentEpicNumber(parkedAt(null, 'blocked'))).toBe(1);
  });
});

describe('skipEpicConfirmLine', () => {
  it('states the ordinary tail: done work still ships', () => {
    expect(skipEpicConfirmLine(1, false)).toBe(
      'skip epic 1: remaining stories are marked skipped, the quality gate re-runs, ' +
        'done work is pushed and the compare link recorded',
    );
  });

  it('states the push_rejected tail: nothing more ships', () => {
    expect(skipEpicConfirmLine(2, true)).toBe(
      'skip epic 2: remaining stories are marked skipped, the quality gate re-runs, ' +
        'the push is skipped',
    );
  });

  it('labels the trigger and confirm button the brief names', () => {
    expect(SKIP_EPIC_LABEL).toBe('Skip epic');
  });
});
