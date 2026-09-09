/**
 * The *Skip story* control's own facts (6.4, FR-20, NFR-8, UX-DR10): which stops offer it,
 * and the sentence its inline confirm states before the signal is posted.
 *
 * Kept beside `answer.ts`/`checkpoint.ts` rather than folded into `detail.ts` for the reason
 * those two already are: this module says what an action will **do**, while that one reads a
 * response. It is also a *sibling* filter rather than a widening — `detail.ts::stopSignals`
 * (`EFFECTIVE_KINDS`), `detail.ts::blockedSignals` and `checkpoint.ts::checkpointSignals` are
 * each pinned by their own frozen test, and this story offers the action on four stops none
 * of them reaches (`verify_failed`, `timeout`, `protected_path`, `internal`).
 *
 * `admitted_signals` still decides: every predicate below reads it, so the button appears
 * exactly where the server says the signal applies and nowhere else. The park kinds are the
 * second half of the rule because the same kind is admitted on stops that have no body of
 * their own to put a control on.
 */
import type { RunDetailOut, SignalKind } from './detail';

/** The stop bodies FR-20 puts *Skip story* on, verbatim from the brief's own binding rule. */
export const SKIP_STORY_STOP_KINDS: readonly string[] = [
  'blocked',
  'checkpoint',
  'verify_failed',
  'timeout',
  'protected_path',
  'misconfigured',
  'internal',
];

/** The confirm's two buttons — the action's own word, and the one that posts nothing. */
export const SKIP_STORY_LABEL = 'Skip story';
export const KEEP_LABEL = 'Keep';

/** The inline confirm line, verbatim (NFR-8: it names the mechanism, including the exact
 * commit message the leftovers land under). */
export function skipStoryConfirmLine(storyId: string): string {
  const id = storyId || 'this story';
  return (
    `skip story ${id}: its remaining steps are marked skipped, the quality gate re-runs, ` +
    `leftovers are committed as "story ${id}: skipped by operator"`
  );
}

/**
 * Whether this stop shows *Skip story*: one of the seven bodies, the Run admits the kind,
 * and the response names the Story it would skip.
 *
 * The third condition is the client-side twin of `rules/signals.py::_has_story_frame`, the
 * `extra` predicate AD-13 gives this kind and `admitted_signals` cannot see (that function
 * answers from the park kind and the row kind alone, and says so in its own docstring). The
 * two agree exactly: a Run parks the strip's `current` cell on whatever frame `park_path` is
 * in, so "no current Story" is "no story frame", which is the case `validate` would refuse
 * with a 409. Without it the confirm would have to name the mechanism it cannot name — no
 * id for the row, and none for the commit message either.
 */
export function offersSkipStory(
  kind: string | null,
  admitted: readonly SignalKind[],
  storyId: string,
): boolean {
  return (
    kind !== null &&
    SKIP_STORY_STOP_KINDS.includes(kind) &&
    admitted.includes('skip_story') &&
    storyId.length > 0
  );
}

/** The Story ids a `done` Run gave up on, or `[]` — what the compare-link line names beside
 * the URL (`{url} · skipped: {ids}`, FR-11). */
export function skippedIds(detail: RunDetailOut): string[] {
  return detail.summary?.skipped ?? [];
}

/** `{url} · skipped: {ids}` for a Run that skipped something, the bare URL otherwise. */
export function compareLinkText(detail: RunDetailOut, url: string): string {
  const ids = skippedIds(detail);
  return ids.length > 0 ? `${url} · skipped: ${ids.join(', ')}` : url;
}
