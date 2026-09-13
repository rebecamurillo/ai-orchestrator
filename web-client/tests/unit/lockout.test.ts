/**
 * The lockout module accepts `now` as a plain number so unit tests can advance time
 * without touching `Date.now()`. Each test uses a unique IP string so the module-level
 * Map does not leak state between cases (the module is imported once per Vitest worker).
 */
import { describe, expect, it } from 'vitest';

import { clear, locked_until, record_failure, remaining } from '../../src/lib/lockout';

const WINDOW_MS = 900_000;
const T0 = Date.UTC(2026, 8, 11, 12, 0, 0); // fixed base time; never Date.now()

describe('initial state', () => {
  it('returns 5 remaining and null locked_until for an unseen IP', () => {
    const ip = 'initial-state';
    expect(remaining(ip, T0)).toBe(5);
    expect(locked_until(ip, T0)).toBeNull();
  });
});

describe('after 4 failures', () => {
  it('shows 1 remaining and no lockout', () => {
    const ip = '4-failures';
    for (let i = 0; i < 4; i++) {
      record_failure(ip, T0 + i);
    }
    const now = T0 + 10;
    expect(remaining(ip, now)).toBe(1);
    expect(locked_until(ip, now)).toBeNull();
  });
});

describe('after 5 failures', () => {
  it('shows 0 remaining and locked_until equals the 5th failure timestamp plus WINDOW_MS', () => {
    const ip = '5-failures';
    for (let i = 0; i < 5; i++) {
      record_failure(ip, T0 + i);
    }
    const T5 = T0 + 4; // 5th failure was recorded here
    const now = T5 + 1;
    expect(remaining(ip, now)).toBe(0);
    expect(locked_until(ip, now)).toBe(T5 + WINDOW_MS);
  });
});

describe('window expiry', () => {
  it('returns 5 remaining and null locked_until after WINDOW_MS elapses past the last failure', () => {
    const ip = 'window-expiry';
    for (let i = 0; i < 5; i++) {
      record_failure(ip, T0 + i);
    }
    const T5 = T0 + 4; // last failure
    // One millisecond after the last failure falls outside the window
    const nowAfterWindow = T5 + WINDOW_MS + 1;
    expect(remaining(ip, nowAfterWindow)).toBe(5);
    expect(locked_until(ip, nowAfterWindow)).toBeNull();
  });
});

describe('clear', () => {
  it('resets the counter so the IP is treated as fresh', () => {
    const ip = 'clear-test';
    for (let i = 0; i < 5; i++) {
      record_failure(ip, T0 + i);
    }
    const now = T0 + 10;
    expect(remaining(ip, now)).toBe(0);

    clear(ip);

    expect(remaining(ip, now)).toBe(5);
    expect(locked_until(ip, now)).toBeNull();
  });
});

describe('rolling window', () => {
  it('does not count a failure that predates the window', () => {
    const ip = 'rolling-window';
    // one failure just outside the 15-minute window
    record_failure(ip, T0 - WINDOW_MS - 1);
    // four failures within the window
    for (let i = 0; i < 4; i++) {
      record_failure(ip, T0 + i * 1_000);
    }
    const now = T0 + 4_000;
    // the outside-window failure does not count: remaining = MAX - 4 = 1
    expect(remaining(ip, now)).toBe(1);
    expect(locked_until(ip, now)).toBeNull();
  });
});
