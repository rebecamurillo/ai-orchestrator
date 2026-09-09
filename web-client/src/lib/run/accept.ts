/**
 * The *Accept changes* control's own facts (6.6, FR-31, AD-17, UX-DR10, NFR-8): which files
 * the Run flagged, how each one is marked, where its diff is, and the body the button posts.
 *
 * **The list comes off `alert.payload.hits`, never off the reason sentence.** The park's own
 * gate record carries one entry per file with the kind AD-17 observed
 * (`rules/protected_paths.py::hits_payload`); `alert.reason` is the same paths joined for a
 * banner, and re-splitting a sentence would invent a parser where the wire already has the
 * list. Read defensively all the same — `payload` is `Record<string, unknown>` on the wire,
 * because `GateRecord.payload` is deliberately open ("whatever the event needs kept").
 *
 * Like `budget.ts`, this widens no frozen filter: `continue` is already in `EFFECTIVE_KINDS`
 * and already renders on the `protected_path` body, so what changes is *how* that one kind
 * renders there — a box that names the files, not a bare `Continue`.
 */
import type { AlertOut, RunDetailOut, SignalKind } from './detail';
import type { SignalIn } from './signals';

/** One file AD-17 flagged, as the body renders it. */
export interface ProtectedHit {
  path: string;
  /** `added` | `deleted` | `modified`, or `''` when the park recorded no kind. */
  kind: string;
}

/** The primary button's word. */
export const ACCEPT_LABEL = 'Accept changes';

/** The mark shown beside each file. `~` also covers a hit whose park recorded no kind —
 * the commit-guard's own rule answers paths only (`ProtectedPaths.check`). */
export function hitMark(kind: string): string {
  if (kind === 'added') return '+';
  if (kind === 'deleted') return '−';
  return '~';
}

/** The files the park recorded, in the order AD-17 reported them. */
export function protectedHits(alert: AlertOut | null | undefined): ProtectedHit[] {
  const entries = alert?.payload?.['hits'];
  if (!Array.isArray(entries)) return [];
  const hits: ProtectedHit[] = [];
  for (const entry of entries) {
    if (typeof entry !== 'object' || entry === null) continue;
    const row = entry as Record<string, unknown>;
    if (typeof row['path'] !== 'string') continue;
    hits.push({ path: row['path'], kind: typeof row['kind'] === 'string' ? row['kind'] : '' });
  }
  return hits;
}

/** Where one file's unified diff is (`GET /runs/{id}/files?path=&diff=1`, 6.6). */
export function diffHref(runId: string, path: string): string {
  return `/api/runs/${runId}/files?path=${encodeURIComponent(path)}&diff=1`;
}

/** What accepting does, once the files are named — the half of the line that never varies. */
const ACCEPT_TAIL = 'the check resumes on the same tree and the files ship with the story';

/**
 * The line above the button, verbatim (NFR-8: it names every consequence).
 *
 * A response that names no current Story still gets a working line — `answer.ts`'s own
 * precedent for exactly this: the signal is admitted either way, and refusing to render the
 * control would strand the Run, so the sentence states the mechanism without inventing an id.
 */
export function acceptLine(storyId: string): string {
  const subject = storyId ? `story ${storyId}` : 'this story';
  return `Accept records these files as accepted for ${subject}; ${ACCEPT_TAIL}`;
}

/** `POST /runs/{id}/signals`'s body for an Accept: exactly the paths the Run reported. */
export function acceptBody(paths: readonly string[]): SignalIn {
  return { kind: 'continue', payload: { files: [...paths] } };
}

/** Whether this stop shows the box: a `protected_path` body whose Run admits `continue`
 * and whose park recorded at least one file to accept. */
export function offersAccept(detail: RunDetailOut, kind: string | null): boolean {
  return (
    kind === 'protected_path' &&
    detail.admitted_signals.includes('continue' as SignalKind) &&
    protectedHits(detail.alert).length > 0
  );
}
