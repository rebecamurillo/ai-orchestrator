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
import { currentStepPath } from './detail';

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

/**
 * *Skip epic*'s own facts (6.5, FR-20, NFR-8, UX-DR10) — deliberately **not** symmetric
 * with the Skip-story predicates above.
 *
 * `admitted_signals(park_kind, row_kind)` cannot run AD-13's own `extra` predicate for this
 * kind either (`rules/signals.py::_has_epic_frame`), but that predicate's two branches are
 * both answerable client-side without a new field: the whole Run is one epic
 * (`run.template_name == "epic"`, published verbatim as `run.template`), or the parked
 * row's own path carries an `epics[n]` frame — the exact same fact `currentEpicNumber`
 * below already reads off `currentStepPath` for the confirm line's own number, reused here
 * rather than approximated by the Run's `template` name a second time (a custom-named copy
 * of an initiative-shaped Template would defeat a name check but not a path one).
 * `offersSkipStory` needed a per-current-Story id because `_has_story_frame` can genuinely
 * be false at a stop that still admits this kind's sibling — reading the path here is both
 * more precise and correct where copying that predicate would refuse the button exactly at
 * `push_rejected`, the one stop this kind adds its own confirm sentence for.
 */
export const SKIP_EPIC_STOP_KINDS: readonly string[] = [
  'blocked',
  'checkpoint',
  'verify_failed',
  'timeout',
  'push_rejected',
  'protected_path',
  'misconfigured',
  'internal',
];

export const SKIP_EPIC_LABEL = 'Skip epic';

//: The bracket `run_views_summary.py::bracket_index` reads off an `epics[n]` frame, read the
//: same way client-side — the parked row's own path is already on the wire
//: (`currentStepPath`, read for `logTail`), so no new field is needed for this.
const EPIC_BRACKET = /epics\[(\d+)\]/;

/** Whether this stop shows *Skip epic*: one of the eight bodies AD-13 admits it on, the Run
 * admits the kind, and `_has_epic_frame`'s own two branches — the whole Run is one epic, or
 * the parked row's own path carries an `epics[n]` frame. */
export function offersSkipEpic(
  detail: RunDetailOut,
  kind: string | null,
  admitted: readonly SignalKind[],
): boolean {
  if (kind === null || !SKIP_EPIC_STOP_KINDS.includes(kind) || !admitted.includes('skip_epic')) {
    return false;
  }
  if (detail.run.template === 'epic') return true;
  const path = currentStepPath(detail);
  return path !== null && EPIC_BRACKET.test(path);
}

/** The 1-based epic number the confirm line names — the brief's own convention
 * (`epics[0]` is "epic 1"), matching `summary.skipped_epics`'s own numbering. `1` for an
 * `epic`-template Run (no bracket at all: it is the one epic) or when no current row path
 * is known yet. */
export function currentEpicNumber(detail: RunDetailOut): number {
  const path = currentStepPath(detail);
  const match = path ? EPIC_BRACKET.exec(path) : null;
  return match ? Number(match[1]) + 1 : 1;
}

/** The inline confirm line, verbatim (NFR-8): the ordinary tail, or the `push_rejected`
 * variant that names what is skipped instead of what still ships. */
export function skipEpicConfirmLine(epicNumber: number, pushRejected: boolean): string {
  const tail = pushRejected
    ? 'the push is skipped'
    : 'done work is pushed and the compare link recorded';
  return (
    `skip epic ${epicNumber}: remaining stories are marked skipped, the quality gate ` +
    `re-runs, ${tail}`
  );
}
