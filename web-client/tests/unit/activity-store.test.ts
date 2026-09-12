/**
 * `src/stores/activity.ts` (8.2): fake-timer unit tests.
 *
 * Four scenarios from the I/O matrix:
 * 1. 60 s with events → one POST fires with `focused_seconds: 60`, accumulated resets.
 * 2. 6 idle minutes → only 300 s counted (idle threshold = 5 min = 300 s);
 *    `lastEventAt` is initialised at `startTracking`; no events dispatched.
 * 3. `visibilityState=hidden` → nothing counted; no POST.
 * 4. `pagehide` with ≥1 accumulated second → remainder posted immediately (sendBeacon).
 *
 * The vitest environment is `node`, so `document` and `window` are not available.
 * This file manually installs minimal event-emitter mocks for the browser APIs the store
 * uses, then tears them down in `afterEach` via `vi.unstubAllGlobals`.
 */
import { EventEmitter } from 'node:events';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '../../src/api/client';

// ---------------------------------------------------------------------------
// Minimal browser-global mocks (node environment only)
// ---------------------------------------------------------------------------

type ListenerFn = () => void;

class FakeEventTarget extends EventEmitter {
  addEventListener(event: string, fn: ListenerFn): void {
    this.on(event, fn);
  }

  removeEventListener(event: string, fn: ListenerFn): void {
    this.off(event, fn);
  }
}

let _visibilityState = 'visible';
let _hasFocus = true;

const fakeDocument = new FakeEventTarget();
Object.defineProperty(fakeDocument, 'visibilityState', {
  configurable: true,
  get: () => _visibilityState,
});
(fakeDocument as unknown as Record<string, unknown>).hasFocus = () => _hasFocus;

const fakeWindow = new FakeEventTarget();

const RUN_ID = 'run-abc-123';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Fire a synthetic pointer event to reset the idle timer inside the store. */
function firePointerEvent(): void {
  fakeDocument.emit('pointermove');
}

function firePagehide(): void {
  fakeWindow.emit('pagehide');
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

let postSpy: ReturnType<typeof vi.fn>;
let beaconSpy: ReturnType<typeof vi.fn>;

// We must import `startTracking`/`stopTracking` lazily (after globals are set) or
// rely on vitest module isolation. Using the dynamic import pattern here keeps the
// module fresh for each test suite run without needing `vi.resetModules()`, because
// the store module-level `_runId` etc. are reset by `stopTracking()` in `afterEach`.
import { startTracking, stopTracking } from '../../src/stores/activity';

beforeEach(() => {
  vi.useFakeTimers();

  _visibilityState = 'visible';
  _hasFocus = true;

  postSpy = vi.spyOn(api, 'POST').mockResolvedValue({} as never);

  beaconSpy = vi.fn().mockReturnValue(true);

  vi.stubGlobal('document', fakeDocument);
  vi.stubGlobal('window', fakeWindow);
  vi.stubGlobal('navigator', { sendBeacon: beaconSpy });
  vi.stubGlobal(
    'Blob',
    class FakeBlob {
      private _content: string;
      constructor(parts: string[]) {
        this._content = parts.join('');
      }
      async text(): Promise<string> {
        return this._content;
      }
    },
  );
});

afterEach(() => {
  stopTracking();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  fakeDocument.removeAllListeners();
  fakeWindow.removeAllListeners();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('activity store', () => {
  it('fires one POST with focused_seconds 60 after 60 s of activity', async () => {
    startTracking(RUN_ID);

    // Advance 1 s at a time, firing a pointer event each tick to keep idle timer fresh.
    for (let i = 0; i < 60; i++) {
      firePointerEvent();
      vi.advanceTimersByTime(1_000);
    }

    // The 60 s batch interval fired at t=60 s via advanceTimersByTime. Drain the async
    // _flush()/_post() chain (2-3 microtask hops) without re-arming the intervals.
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(postSpy).toHaveBeenCalledOnce();
    const [, opts] = postSpy.mock.calls[0] as [string, { body: { focused_seconds: number } }];
    expect(opts.body).toEqual({ focused_seconds: 60 });
  });

  it('counts only 300 s when idle for 6 minutes (idle threshold = 5 min)', async () => {
    startTracking(RUN_ID);

    // Advance 360 s with no events. `lastEventAt` was set at startTracking (t=0).
    // Seconds 1-300: Date.now() - t0 ≤ 300,000 ms → counted.
    // Seconds 301-360: Date.now() - t0 > 300,000 ms → not counted.
    // Batches fire at 60, 120, 180, 240, 300 s (5 × 60 = 300 total).
    // At second 360, the 6th batch fires but accumulated = 0 (no seconds counted).
    vi.advanceTimersByTime(360_000);
    // Drain 5 concurrent _flush()/_post() chains (all at same depth — 3 rounds suffice).
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    const totalPosted = (
      postSpy.mock.calls as [string, { body: { focused_seconds: number } }][]
    ).reduce((sum, [, opts]) => sum + opts.body.focused_seconds, 0);
    expect(totalPosted).toBe(300);
  });

  it('counts nothing when visibilityState is hidden', async () => {
    _visibilityState = 'hidden';

    startTracking(RUN_ID);

    // Advance 65 s — enough for a batch interval to trigger if counting were active.
    vi.advanceTimersByTime(65_000);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    // No POST should have fired (accumulated stays at 0).
    expect(postSpy).not.toHaveBeenCalled();
  });

  it('flushes remainder via sendBeacon on pagehide when accumulated >= 1', async () => {
    startTracking(RUN_ID);

    // Accumulate 30 s (well within the 60 s batch window, so no batch fires yet).
    for (let i = 0; i < 30; i++) {
      firePointerEvent();
      vi.advanceTimersByTime(1_000);
    }

    firePagehide();

    expect(beaconSpy).toHaveBeenCalledOnce();
    const [url, blob] = beaconSpy.mock.calls[0] as [string, { text: () => Promise<string> }];
    expect(url).toContain(`/runs/${RUN_ID}/activity`);
    const text = await blob.text();
    expect(JSON.parse(text)).toEqual({ focused_seconds: 30 });
  });

  it('does not POST on pagehide when accumulated is 0', async () => {
    _visibilityState = 'hidden';

    startTracking(RUN_ID);
    vi.advanceTimersByTime(1_000);

    firePagehide();

    expect(beaconSpy).not.toHaveBeenCalled();
    expect(postSpy).not.toHaveBeenCalled();
  });
});
