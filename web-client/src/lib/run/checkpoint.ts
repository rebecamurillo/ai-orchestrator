/**
 * The checkpoint bodies' own facts (6.2, FR-19, UX-DR10): which of the two `StopBody`
 * `checkpoint` cases applies (`alert.row_kind`), the Reject box's hint, the planned file's
 * glob path, and the done-checkpoint's own summary line.
 *
 * Kept beside `answer.ts` rather than folded into it: Reject reuses that module's `answer`
 * wire shape (`{kind: 'answer', payload: {text}}`) and its `AnswerTarget`/`answerTarget`,
 * but the copy and the two admission rules below are this story's own.
 */
import type { AnswerTarget } from './answer';
import { ARCHIVE_PATH } from './answer';
import type { AttributionOut, CheckpointStoryOut, RunDetailOut, SignalKind } from './detail';

//: The extra kinds a `checkpoint` stop's own button row offers, beside `continue`
//: (`stopSignals`'s three `EFFECTIVE_KINDS` already give every stop) — the same two skips
//: `blockedSignals` already renders for `blocked`/`misconfigured` (5.10), admitted here too
//: (brief's own binding rule: "also *Skip story*, *Skip epic*, *Cancel run*"). Kept apart
//: from `EFFECTIVE_KINDS`: that stays the exact three kinds the frozen `run-detail-lib.
//: test.ts` pins for every *other* park kind.
const CHECKPOINT_EXTRA_KINDS: readonly SignalKind[] = ['continue', 'skip_story', 'skip_epic'];

/** `admitted_signals`, narrowed to the kinds a `checkpoint` stop's own button row renders —
 * never `answer` (`RejectBox`'s own control), never `cancel` (`StopBody`'s own dedicated
 * button, `stopSignals`/`blockedSignals`' shared precedent). */
export function checkpointSignals(admitted: readonly SignalKind[]): SignalKind[] {
  return admitted.filter((kind) => CHECKPOINT_EXTRA_KINDS.includes(kind));
}

/** The hint under the Reject textarea, verbatim (brief's own binding rule). */
export const REJECT_HINT =
  `planned story archived to ${ARCHIVE_PATH} with your reason; ` + 'story {id} re-planned';

/** The link that reveals the textarea, and the button that submits it. */
export const REJECT_TOGGLE_LABEL = 'Reject with a reason';
export const REJECT_LABEL = 'Reject and re-plan';

/** The hint line for one target — `answerHint`'s own substitution, this story's own words. */
export function rejectHint(target: AnswerTarget): string {
  return REJECT_HINT.replaceAll('{id}', target.storyId).replace('{n}', String(target.attempt));
}

/** A `checkpoint` stop on the `agent` row itself: the plan is not yet approved, so the
 * screen shows the planned file, not a done-checkpoint summary. */
export function isSpecCheckpoint(detail: RunDetailOut, kind: string | null): boolean {
  return kind === 'checkpoint' && detail.alert?.row_kind === 'agent';
}

/** A `checkpoint` stop on any other row: the Story frame already finished. `row_kind`
 * missing entirely (a response predating this story) is neither case, so the generic
 * banner `StopBody` already rendered for `checkpoint` stays exactly as it was. */
export function isDoneCheckpoint(detail: RunDetailOut, kind: string | null): boolean {
  const rowKind = detail.alert?.row_kind;
  return kind === 'checkpoint' && rowKind != null && rowKind !== 'agent';
}

/** Whether this stop offers Reject: a spec checkpoint whose Run admits `answer` — the same
 * signal 6.1's Answer box posts, at a different park (`AnswerBox`'s own precedent). */
export function offersReject(detail: RunDetailOut, kind: string | null): boolean {
  return isSpecCheckpoint(detail, kind) && detail.admitted_signals.includes('answer');
}

/** `{spec_folder}/stories/{id}-*.md` — the glob `GET /runs/{id}/files` resolves server-side
 * (brief's own words), built from the current Story cell the same way `answer.ts::
 * answerTarget` reads it. `null` when the response names no current Story to plan for. */
export function plannedFilePath(detail: RunDetailOut): string | null {
  const current = detail.stories.find((cell) => cell.state === 'current');
  if (!current) return null;
  return `${detail.header.meta.folder}/stories/${current.story_id}-*.md`;
}

/** The spec-checkpoint body's own eyebrow (UX-DR9's own shape, this story's own label):
 * `planned by {harness} · {model} · {time}`, `—` for a part the attempt never recorded. */
export function plannedEyebrow(attribution: AttributionOut | null | undefined): string {
  const harness = attribution?.harness ?? '—';
  const model = attribution?.model ?? '—';
  const endedAt = attribution?.ended_at ?? '—';
  return `planned by ${harness} · ${model} · ${endedAt}`;
}

/** The done-checkpoint's own summary line, verbatim (brief's own binding rule): `story {id}
 * · {title} · {attempts} attempts · ${cost} · verify {done|skipped}`. */
export function checkpointSummaryLine(story: CheckpointStoryOut): string {
  const verify = story.verify === 'skipped' ? 'skipped' : 'done';
  return (
    `story ${story.story_id} · ${story.title} · ${story.attempts} attempts · ` +
    `$${story.cost_usd} · verify ${verify}`
  );
}
