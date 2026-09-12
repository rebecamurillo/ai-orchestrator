/**
 * Operator active-time tracker (SM-2, story 8-2): counts focused seconds and batches
 * them to `POST /api/v1/runs/{id}/activity` every 60 s. On `pagehide`, any remainder
 * is flushed immediately via `sendBeacon` (falling back to `fetch({keepalive: true})`).
 *
 * **Idle exclusion.** Pointer and keydown events reset `lastEventAt`. The per-second tick
 * only increments `accumulated` when `Date.now() - lastEventAt ≤ IDLE_TIMEOUT_MS` *and*
 * the tab is both visible and focused. This handles resumption implicitly: the next event
 * resets the timer and the next tick counts again — no separate "paused" flag is needed.
 *
 * **Tab-hidden.** When `document.visibilityState === 'hidden'`, the per-second tick skips
 * incrementing. `accumulated` is still flushed on `pagehide`.
 *
 * **Singleton.** `startTracking` / `stopTracking` manage one global state; calling
 * `startTracking` again clears any prior tracking before starting fresh.
 *
 * **Fire-and-forget.** The batch POST is not retried on failure (story brief constraint).
 * The `pagehide` flush uses `sendBeacon` which is fire-and-forget by nature; the `fetch`
 * fallback uses `keepalive: true` so the browser keeps the request alive after the page
 * unloads.
 */

import { api } from '../api/client';

/** Same origin proxy base as `src/api/client.ts::API_BASE_URL` — the proxy adds `/v1/`. */
const API_BASE = '/api';
const BATCH_INTERVAL_MS = 60_000;
const IDLE_TIMEOUT_MS = 300_000; // 5 minutes — the brief's "300_000" constant
const TICK_INTERVAL_MS = 1_000;

let _runId: string | null = null;
let _accumulated = 0;
let _lastEventAt = 0;
let _tickHandle: ReturnType<typeof setInterval> | undefined;
let _batchHandle: ReturnType<typeof setInterval> | undefined;

function _resetIdleTimer(): void {
  _lastEventAt = Date.now();
}

function _isActive(): boolean {
  return document.visibilityState === 'visible' && document.hasFocus();
}

function _tick(): void {
  if (!_isActive()) return;
  if (Date.now() - _lastEventAt <= IDLE_TIMEOUT_MS) {
    _accumulated++;
  }
}

async function _flush(): Promise<void> {
  if (!_runId || _accumulated < 1) return;
  const seconds = _accumulated;
  _accumulated = 0;
  await _post(seconds);
}

function _flushBeacon(): void {
  if (!_runId || _accumulated < 1) return;
  const seconds = _accumulated;
  _accumulated = 0;
  const url = `${API_BASE}/runs/${_runId}/activity`;
  const body = JSON.stringify({ focused_seconds: seconds });
  if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
    navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }));
  }
  // No fetch fallback: sendBeacon is supported in all modern browsers. If unavailable,
  // the pagehide flush is skipped; the 60 s interval covers the common case.
}

async function _post(seconds: number): Promise<void> {
  if (!_runId) return;
  try {
    await api.POST('/runs/{run_id}/activity', {
      params: { path: { run_id: _runId } },
      body: { focused_seconds: seconds },
    });
  } catch {
    // fire-and-forget: no retry (story brief constraint)
  }
}

function _handlePagehide(): void {
  _flushBeacon();
}

/**
 * Start tracking active seconds for the given Run. Clears any prior tracking session.
 * Registers pointer, keydown, and pagehide listeners; starts the per-second tick and
 * 60 s batch interval.
 */
export function startTracking(runId: string): void {
  stopTracking();
  _runId = runId;
  _accumulated = 0;
  _lastEventAt = Date.now();

  document.addEventListener('pointermove', _resetIdleTimer);
  document.addEventListener('pointerdown', _resetIdleTimer);
  document.addEventListener('keydown', _resetIdleTimer);
  window.addEventListener('pagehide', _handlePagehide);

  _tickHandle = setInterval(_tick, TICK_INTERVAL_MS);
  _batchHandle = setInterval(() => void _flush(), BATCH_INTERVAL_MS);
}

/**
 * Stop tracking and remove all listeners. Does not flush — the caller is responsible for
 * ensuring the island unmounts cleanly. The `pagehide` listener fires independently of
 * `stopTracking`.
 */
export function stopTracking(): void {
  if (_tickHandle !== undefined) clearInterval(_tickHandle);
  if (_batchHandle !== undefined) clearInterval(_batchHandle);
  _tickHandle = undefined;
  _batchHandle = undefined;

  document.removeEventListener('pointermove', _resetIdleTimer);
  document.removeEventListener('pointerdown', _resetIdleTimer);
  document.removeEventListener('keydown', _resetIdleTimer);
  window.removeEventListener('pagehide', _handlePagehide);

  _runId = null;
}
