/**
 * The one polling loop (FR-24, `web-client/AGENTS.md`): `$poll` ticks every 5 s while any Run
 * is running, else 30 s. `Board.tsx` is the first subscriber; a later Run detail island
 * (4.15) reuses this same store rather than opening a second interval, which is the whole
 * point of naming it here instead of inside the island.
 *
 * `$poll` carries a bare tick counter, not a timestamp or the data itself — `template-
 * validation.ts`'s `seq` is the same shape for the same reason: a subscriber only needs to
 * know "something changed", and a counter is what lets `useStore` see two ticks a second
 * apart as two distinct values.
 *
 * The interval is owned here, not by the island's own `setInterval`, so that switching
 * between 5 s and 30 s never straddles two timers: `configurePolling` always clears the
 * previous one before starting the next.
 */
import { atom } from 'nanostores';

export const FAST_MS = 5_000;
export const SLOW_MS = 30_000;

/** Ticks up on every poll, automatic or forced. */
export const $poll = atom(0);

let timer: ReturnType<typeof setInterval> | undefined;
let currentIntervalMs: number | undefined;

function tick(): void {
  $poll.set($poll.get() + 1);
}

/**
 * Start or re-time the interval. Idempotent at the same cadence — called after every poll
 * result, so a run of "still running" results must not restart the timer each time (that
 * would never let a full 5 s elapse).
 */
export function configurePolling(hasRunning: boolean): void {
  const intervalMs = hasRunning ? FAST_MS : SLOW_MS;
  if (currentIntervalMs === intervalMs) return;
  currentIntervalMs = intervalMs;
  if (timer !== undefined) clearInterval(timer);
  timer = setInterval(tick, intervalMs);
}

/** The *refresh* control: one immediate tick, independent of the interval's own schedule. */
export function forceTick(): void {
  tick();
}

/** Stops the interval — a poll that just failed must not keep ticking until Retry. */
export function stopPolling(): void {
  if (timer !== undefined) clearInterval(timer);
  timer = undefined;
  currentIntervalMs = undefined;
}
