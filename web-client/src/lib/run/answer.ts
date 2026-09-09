/**
 * The Answer box's own facts (6.1, FR-18, UX-DR10, UX-DR17): which file the Run will archive,
 * the sentence that says so, and the body the button posts.
 *
 * Kept out of `detail.ts` because that module is the *response* reader and this is the one
 * place a screen has to say what a signal will **do** — the same split `signals.ts` already
 * draws for the request bodies.
 *
 * **The copy names the mechanism, and only what it knows** (NFR-8). A `blocked` stop on an
 * agent row always carries the Story it is on, so the hint names the exact archive path. A
 * response that carries no current Story still gets a working box — the signal is admitted
 * either way, and refusing to render it would strand the Run — but its hint states the
 * directory and the re-plan without inventing a file name it cannot know.
 */
import type { SignalIn } from './signals';
import { currentStepPath, stepAt, type RunDetailOut, type StepRowOut } from './detail';

/** The archive FR-18 pins, as the hint spells it. */
export const ARCHIVE_PATH = 'stories/.answers/{id}-attempt-{n}.md';

/** The hint under the textarea, verbatim (UX-DR17). */
export const ANSWER_HINT =
  `Blocked story file archived to ${ARCHIVE_PATH} with your answer; ` +
  'story {id} re-planned with the answer as context. ' +
  'If the gap is in SPEC.md, edit SPEC.md on the branch instead.';

/** The same sentence for a response that names no Story — the mechanism, no invented path. */
export const ANSWER_HINT_WITHOUT_STORY =
  'Blocked story file archived to stories/.answers/ with your answer; ' +
  'the story is re-planned with the answer as context. ' +
  'If the gap is in SPEC.md, edit SPEC.md on the branch instead.';

/** The button, and the box's own test ids. */
export const ANSWER_LABEL = 'Resume with answer';

export interface AnswerTarget {
  /** The Story the Run is parked on, or `''` when the response names none. */
  storyId: string;
  /** The attempt whose Story file is about to be archived — the one that blocked. */
  attempt: number;
}

/**
 * What the resumed attempt will archive, read off the response and never derived twice: the
 * Story is the `current` cell of the strip, and the attempt is the parked row's latest.
 */
export function answerTarget(detail: RunDetailOut): AnswerTarget {
  const current = detail.stories.find((cell) => cell.state === 'current');
  const row = parkedRow(detail);
  return { storyId: current?.story_id ?? '', attempt: row?.latest?.n ?? row?.attempts ?? 1 };
}

/** The row the Run stopped on: the one the gate record names, or — for a response whose
 * record has not been read yet — the `blocked` row itself, which is the same row by
 * definition. Never a guess: if neither names one, the caller falls back to attempt 1. */
function parkedRow(detail: RunDetailOut): StepRowOut | undefined {
  return (
    stepAt(detail.steps, currentStepPath(detail)) ??
    detail.steps.find((step) => step.status === 'blocked')
  );
}

/** The hint line for one target. */
export function answerHint(target: AnswerTarget): string {
  if (!target.storyId) return ANSWER_HINT_WITHOUT_STORY;
  return ANSWER_HINT.replaceAll('{id}', target.storyId).replace('{n}', String(target.attempt));
}

/** `POST /runs/{id}/signals`'s body for an Answer: the Operator's text, under `text`. */
export function answerBody(text: string): SignalIn {
  return { kind: 'answer', payload: { text } };
}

/** Whether this stop offers the Answer box: a `blocked` body whose Run admits `answer`. */
export function offersAnswer(detail: RunDetailOut, kind: string | null): boolean {
  return kind === 'blocked' && detail.admitted_signals.includes('answer');
}
