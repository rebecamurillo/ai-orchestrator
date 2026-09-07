/**
 * `src/lib/run/signals.ts` (4.15, 4.9's own contract): the `POST /runs/{id}/signals` body
 * each control on the Run detail posts.
 */
import { describe, expect, it } from 'vitest';

import { signalBody, signalLabel, signalsRequestPath } from '../../src/lib/run/signals';

describe('signalBody', () => {
  it('carries no payload for continue and retry', () => {
    expect(signalBody('continue')).toEqual({ kind: 'continue' });
    expect(signalBody('retry')).toEqual({ kind: 'retry' });
  });

  it('carries confirm: true for cancel', () => {
    expect(signalBody('cancel')).toEqual({ kind: 'cancel', payload: { confirm: true } });
  });
});

describe('signalsRequestPath', () => {
  it('is the runs/{id}/signals path', () => {
    expect(signalsRequestPath('r1')).toBe('/api/runs/r1/signals');
  });
});

describe('signalLabel', () => {
  it('reads the button word for each kind this epic offers', () => {
    expect(signalLabel('continue')).toBe('Continue');
    expect(signalLabel('retry')).toBe('Retry');
    expect(signalLabel('cancel')).toBe('Cancel run');
  });
});
