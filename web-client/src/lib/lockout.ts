/**
 * Per-IP login lockout (AD-4). Pure in-memory; never touches the database or disk.
 *
 * A rolling 15-minute window tracks wrong-token submissions per IP. After 5 failures
 * within the window the IP is locked until the 5th failure's timestamp + WINDOW_MS. A
 * successful login calls `clear(ip)` and resets the counter to zero.
 *
 * Every public function accepts a `now` timestamp (plain number, milliseconds) so unit
 * tests can advance time without patching `Date.now()`. Production callers pass
 * `Date.now()` directly.
 */

const WINDOW_MS = 900_000; // 15 minutes in milliseconds
const MAX = 5; // failures before lockout

// Module-level store — intentionally in-process only; restart resets all counters.
const failures = new Map<string, number[]>();

/** Failure timestamps for `ip` that fall within the rolling window ending at `now`. */
function windowEntries(ip: string, now: number): number[] {
  return (failures.get(ip) ?? []).filter((t) => t > now - WINDOW_MS);
}

/**
 * Record one wrong-token failure for `ip` at time `now`.
 * Old entries outside the window are pruned on each write to keep the store bounded.
 */
export function record_failure(ip: string, now: number): void {
  const entries = windowEntries(ip, now);
  entries.push(now);
  failures.set(ip, entries);
}

/**
 * How many more wrong tokens the IP may submit before being locked.
 * Returns 5 for an unseen IP and 0 for a locked one.
 */
export function remaining(ip: string, now: number): number {
  return Math.max(0, MAX - windowEntries(ip, now).length);
}

/**
 * The timestamp (ms) at which the lockout for `ip` lifts, or `null` if not locked.
 * The lock lasts until the 5th failure's timestamp plus `WINDOW_MS`; at that point the
 * failure falls outside the window and the counter resets naturally.
 */
export function locked_until(ip: string, now: number): number | null {
  const entries = windowEntries(ip, now);
  if (entries.length >= MAX) {
    return entries[MAX - 1]! + WINDOW_MS;
  }
  return null;
}

/** Remove all failure history for `ip`. Call on a successful login. */
export function clear(ip: string): void {
  failures.delete(ip);
}
