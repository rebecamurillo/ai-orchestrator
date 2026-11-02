/**
 * Story 2-1, CAP-8: what the Run page knows about a pause. `paused` renders `CHK`, `pause`
 * is offered only where `admitted_signals` lists it, and the request carries no `stop`.
 */
import { describe, expect, it } from 'vitest';

import { runToken, stopKind, type AlertOut, type RunDetailOut } from '../../src/lib/run/detail';
import { PAUSE_CONFIRM_LINE, PAUSE_REQUESTED_LINE, offersPause } from '../../src/lib/run/pause';
import { signalBody, signalLabel, withStop } from '../../src/lib/run/signals';

function run(status: RunDetailOut['run']['status']): RunDetailOut['run'] {
  return { status } as RunDetailOut['run'];
}

function alert(parkKind: string): AlertOut {
  return { park_kind: parkKind } as unknown as AlertOut;
}

describe('runToken · paused', () => {
  it('renders a paused stop as CHK, like a checkpoint', () => {
    expect(runToken(run('needs_you'), alert('paused'))).toBe('CHK');
    expect(runToken(run('needs_you'), alert('checkpoint'))).toBe('CHK');
  });

  it('still renders every other stop as BLK', () => {
    expect(runToken(run('needs_you'), alert('blocked'))).toBe('BLK');
    expect(runToken(run('needs_you'), alert('merge_conflict'))).toBe('BLK');
  });

  it('keeps RUN for a running Run that has been asked to pause', () => {
    expect(runToken(run('running'), null)).toBe('RUN');
  });
});

describe('stopKind · paused', () => {
  it('gives a paused stop its own body', () => {
    const detail = { alert: alert('paused') } as unknown as RunDetailOut;

    expect(stopKind(detail, 'CHK')).toBe('paused');
  });
});

describe('offersPause', () => {
  it('is true only when the server lists pause', () => {
    expect(offersPause(['pause', 'cancel'])).toBe(true);
    expect(offersPause(['cancel'])).toBe(false);
    expect(offersPause(['continue', 'cancel'])).toBe(false);
  });
});

describe('the pause request', () => {
  it('is a bare signal that names no stop', () => {
    expect(signalBody('pause')).toEqual({ kind: 'pause' });
    expect(withStop({ kind: 'pause' }, 4)).toEqual({ kind: 'pause' });
  });

  it('reads Pause on its button', () => {
    expect(signalLabel('pause')).toBe('Pause');
  });

  it('states the mechanism before and after the request', () => {
    expect(PAUSE_CONFIRM_LINE).toContain('nothing is killed');
    expect(PAUSE_CONFIRM_LINE).toContain('current step finishes');
    expect(PAUSE_REQUESTED_LINE).toContain('when the current step ends');
  });
});
