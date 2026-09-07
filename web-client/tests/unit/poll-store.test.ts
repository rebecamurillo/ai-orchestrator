/**
 * `src/stores/poll.ts` (4.14, FR-24, `web-client/AGENTS.md`'s "one polling loop"): `$poll`
 * ticks every 5s while something is running, else 30s; `forceTick` ticks once immediately
 * (the *refresh* control); `stopPolling` clears the interval (a failed fetch pauses polling
 * until Retry succeeds).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  $poll,
  FAST_MS,
  SLOW_MS,
  configurePolling,
  forceTick,
  stopPolling,
} from '../../src/stores/poll';

beforeEach(() => {
  vi.useFakeTimers();
  $poll.set(0);
});

afterEach(() => {
  stopPolling();
  vi.useRealTimers();
});

describe('$poll', () => {
  it('ticks every 5s while something is running', () => {
    configurePolling(true);
    vi.advanceTimersByTime(FAST_MS * 2);
    expect($poll.get()).toBe(2);
  });

  it('ticks every 30s once nothing is running', () => {
    configurePolling(false);
    vi.advanceTimersByTime(SLOW_MS * 2);
    expect($poll.get()).toBe(2);
  });

  it('re-arms the interval at the new cadence on a change, not the old one', () => {
    configurePolling(true);
    vi.advanceTimersByTime(FAST_MS);
    expect($poll.get()).toBe(1);

    configurePolling(false);
    vi.advanceTimersByTime(SLOW_MS - FAST_MS);
    expect($poll.get()).toBe(1);
    vi.advanceTimersByTime(FAST_MS);
    expect($poll.get()).toBe(2);
  });

  it('does not restart the timer for the same cadence twice in a row', () => {
    configurePolling(true);
    vi.advanceTimersByTime(FAST_MS - 1);
    configurePolling(true);
    vi.advanceTimersByTime(1);
    expect($poll.get()).toBe(1);
  });

  it('forceTick ticks immediately, independent of the interval', () => {
    forceTick();
    expect($poll.get()).toBe(1);
  });

  it('stopPolling clears the interval', () => {
    configurePolling(true);
    stopPolling();
    vi.advanceTimersByTime(FAST_MS * 3);
    expect($poll.get()).toBe(0);
  });
});
