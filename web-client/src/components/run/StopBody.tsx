/**
 * The stop body (4.15, UX-DR10): what stopped the Run, in words and — where the park kind
 * has one — a log tail, then the buttons `admitted_signals` and the effects that have landed
 * (`cancel`, `retry`, `continue`; `answer` 6.1, `skip_story` 6.4, `skip_epic` 6.5) both allow.
 * Three signals do not render as buttons at all, because each carries something a button
 * cannot ask for: the Answer's text (6.1), the raised budget's figure and the Accept's file
 * list (both 6.6). Each is a box of its own, offered only where `admitted_signals` says so.
 * `park_kind`-keyed rather than
 * a name-per-component split: every variant but `plan_stale` renders the same shape (a
 * reason, an optional command block, the button row), so one switch reads truer than seven
 * near-identical files.
 *
 * No `plan-diff` panel: see `src/lib/run/detail.ts`'s own module doc for why the `plan_stale`
 * body below shows the reason and path only, not the line-diff the brief's brief-authored
 * `[ASSUMPTION]` asked for.
 *
 * Stateless — every signal click is reported upward (`onSignal`/`onCancelClick`); the island
 * owns the in-flight and 409 state, the same split `NewWorkflow.tsx` draws between its own
 * state and `PreflightLines`/`PlanTable`.
 */
import type { components } from '../../api/schema';
import type { RunDetailOut, Token } from '../../lib/run/detail';
import {
  bannerText,
  blockedSignals,
  currentStepPath,
  logTail,
  misconfiguredFiles,
  stepAt,
  stopKind,
  stopSignals,
} from '../../lib/run/detail';
import { offersAccept, protectedHits } from '../../lib/run/accept';
import { answerTarget, offersAnswer } from '../../lib/run/answer';
import { offersBudgetRaise } from '../../lib/run/budget';
import {
  checkpointSignals,
  checkpointSummaryLine,
  isDoneCheckpoint,
  isSpecCheckpoint,
  offersReject,
  plannedEyebrow,
} from '../../lib/run/checkpoint';
import { signalLabel, type SignalKind } from '../../lib/run/signals';
import {
  KEEP_LABEL,
  SKIP_EPIC_LABEL,
  SKIP_STORY_LABEL,
  currentEpicNumber,
  offersSkipEpic,
  offersSkipStory,
  skipEpicConfirmLine,
  skipStoryConfirmLine,
} from '../../lib/run/skip';
import AcceptBox from './AcceptBox';
import AnswerBox from './AnswerBox';
import BudgetRaiseBox from './BudgetRaiseBox';
import ConfirmAction from './ConfirmAction';
import QuestionBlock from './QuestionBlock';
import RejectBox from './RejectBox';
import StoryFileBlock from './StoryFileBlock';

type ProblemDetail = components['schemas']['ProblemDetail'];
type RunFileOut = components['schemas']['RunFileOut'];

interface Props {
  detail: RunDetailOut;
  token: Token;
  onSignal: (kind: SignalKind) => void;
  onCancelClick: () => void;
  posting: SignalKind | null;
  error: ProblemDetail | null;
  /** The Answer (6.1, FR-18) and the Reject (6.2, FR-19) — the two signals that carry a
   * payload, so they are reported with their text rather than by kind alone. Both post the
   * same `answer` signal (`AnswerBox`/`RejectBox`'s own precedent), so one callback serves
   * both boxes. Optional because neither box appears outside the one stop that admits it,
   * and a caller that renders no such stop has nothing to hand it. */
  onAnswer?: (text: string) => void;
  /** The raised budget (6.6, FR-17) — a figure, so like the Answer it is reported with its
   * payload rather than by kind alone. Optional for the same reason: no other stop has one. */
  onRaiseBudget?: (budgetUsd: string) => void;
  /** The accepted protected paths (6.6, FR-31) — always exactly the files the park recorded,
   * which is what the server refuses any other list against. */
  onAccept?: (paths: string[]) => void;
  /** This Run's id, for the per-file diff links the protected-path body renders. */
  runId?: string;
  /** The planned story file a spec checkpoint shows inline (`GET /runs/{id}/files`) —
   * fetched by the island, since `StopBody` itself stays stateless. `undefined` while it
   * has not resolved yet, `null` on a failed fetch. */
  plannedFile?: RunFileOut | null;
}

const RESOLVE_LINE = 'resolve on the remote, then Retry — Retry fetches first';
const PLAN_STALE_NOTE = 're-read the file on the branch to see what changed';

export default function StopBody({
  detail,
  token,
  onSignal,
  onCancelClick,
  posting,
  error,
  onAnswer = () => {},
  onRaiseBudget = () => {},
  onAccept = () => {},
  runId = '',
  plannedFile = null,
}: Props) {
  const kind = stopKind(detail, token);
  if (kind === null) return null;

  const isQuestion = kind === 'blocked' || kind === 'misconfigured';
  const offered = isQuestion
    ? blockedSignals(detail.admitted_signals)
    : kind === 'checkpoint'
      ? checkpointSignals(detail.admitted_signals)
      : stopSignals(detail.admitted_signals);
  // FR-20 puts *Skip story* on four stops none of the three filters above reaches
  // (`verify_failed`, `timeout`, `protected_path`, `internal`), and it renders as a confirm
  // wherever it appears. Appending rather than widening any of them keeps each one's own
  // frozen test true; `offersSkipStory` reads `admitted_signals`, so the server still decides.
  const skipStoryId = answerTarget(detail).storyId;
  const withSkipStory =
    offersSkipStory(kind, detail.admitted_signals, skipStoryId) && !offered.includes('skip_story')
      ? [...offered, 'skip_story' as SignalKind]
      : offered;
  const skipStoryLine = skipStoryConfirmLine(skipStoryId);
  // *Skip epic* already renders as a plain button on three of the eight stops it is
  // admitted on (`blockedSignals`/`checkpointSignals`, 5.10/6.2) — this appends it, as a
  // confirm, on the remaining five (`verify_failed`, `timeout`, `protected_path`,
  // `internal`, `push_rejected`), the same sibling-filter pattern `offersSkipStory` uses.
  const signals =
    offersSkipEpic(detail, kind, detail.admitted_signals) && !withSkipStory.includes('skip_epic')
      ? [...withSkipStory, 'skip_epic' as SignalKind]
      : withSkipStory;
  const skipEpicLine = skipEpicConfirmLine(currentEpicNumber(detail), kind === 'push_rejected');
  // The Accept *is* `continue` on this stop, and it posts a payload — so the plain button
  // for that kind steps aside here, exactly as `skip_story`'s does for its confirm. Every
  // other stop's `continue` button is untouched (`plan_stale`, `checkpoint`).
  const accepting = offersAccept(detail, kind);
  const buttons = accepting ? signals.filter((s) => s !== 'continue') : signals;
  const canCancel = detail.admitted_signals.includes('cancel');
  const tail = logTail(detail);
  const path = currentStepPath(detail);
  const row = stepAt(detail.steps, path);
  const files = kind === 'misconfigured' ? misconfiguredFiles(detail.alert?.reason) : [];

  return (
    <div className="wf-stop" data-testid={`wf-stop-${kind}`}>
      {kind === 'blocked' && detail.alert ? <QuestionBlock alert={detail.alert} /> : null}
      {offersAnswer(detail, kind) ? (
        <AnswerBox
          target={answerTarget(detail)}
          onAnswer={onAnswer}
          posting={posting !== null}
          error={posting === null && error ? error : null}
        />
      ) : null}
      {kind === 'misconfigured' ? <p className="wf-stop-reason">{bannerText(detail)}</p> : null}
      {files.length > 0 ? (
        <ul className="wf-stop-files" data-testid="wf-stop-files">
          {files.map((file) => (
            <li key={file}>{file}</li>
          ))}
        </ul>
      ) : null}
      {kind === 'plan_stale' ? <PlanStaleBody detail={detail} /> : null}
      {kind === 'push_rejected' ? <p className="wf-stop-reason">{RESOLVE_LINE}</p> : null}
      {kind === 'budget' ? <p className="wf-stop-reason">{bannerText(detail)}</p> : null}
      {offersBudgetRaise(kind, detail.admitted_signals) ? (
        <BudgetRaiseBox
          cost={detail.cost}
          onRaise={onRaiseBudget}
          posting={posting !== null}
          error={posting === null && error ? error : null}
        />
      ) : null}
      {kind === 'protected_path' ? <p className="wf-stop-reason">{bannerText(detail)}</p> : null}
      {accepting ? (
        <AcceptBox
          runId={runId}
          hits={protectedHits(detail.alert)}
          storyId={skipStoryId}
          onAccept={onAccept}
          posting={posting !== null}
        />
      ) : null}
      {kind === 'checkpoint' ? <p className="wf-stop-reason">{bannerText(detail)}</p> : null}
      {isSpecCheckpoint(detail, kind) ? (
        <>
          {plannedFile ? (
            <StoryFileBlock
              eyebrow={plannedEyebrow(detail.alert?.attribution)}
              content={plannedFile.content}
            />
          ) : null}
          {offersReject(detail, kind) ? (
            <RejectBox
              target={answerTarget(detail)}
              onReject={onAnswer}
              posting={posting !== null}
              error={posting === null && error ? error : null}
            />
          ) : null}
        </>
      ) : null}
      {isDoneCheckpoint(detail, kind) && detail.alert?.checkpoint_story ? (
        <p className="wf-checkpoint-summary" data-testid="wf-checkpoint-summary">
          {checkpointSummaryLine(detail.alert.checkpoint_story)}
        </p>
      ) : null}
      {kind === 'failed' ? (
        <p className="wf-stop-reason">{row ? `${row.path} · ${row.label}` : ''}</p>
      ) : null}

      {tail.length > 0 ? (
        <figure className="wf-stop-block">
          <figcaption className="wf-stop-block-head">LOG TAIL</figcaption>
          <pre>{tail.join('\n')}</pre>
        </figure>
      ) : null}

      {kind === 'failed' ? (
        <p>
          <a className="wf-new-run-link" href="/workflows/new">
            start a new run
          </a>
        </p>
      ) : (
        <div className="wf-stop-actions">
          {buttons.map((s) =>
            s === 'skip_story' ? (
              <ConfirmAction
                key={s}
                kind={s}
                label={SKIP_STORY_LABEL}
                line={skipStoryLine}
                confirmLabel={SKIP_STORY_LABEL}
                keepLabel={KEEP_LABEL}
                disabled={posting !== null}
                onConfirm={() => onSignal(s)}
              />
            ) : s === 'skip_epic' ? (
              <ConfirmAction
                key={s}
                kind={s}
                label={SKIP_EPIC_LABEL}
                line={skipEpicLine}
                confirmLabel={SKIP_EPIC_LABEL}
                keepLabel={KEEP_LABEL}
                disabled={posting !== null}
                onConfirm={() => onSignal(s)}
              />
            ) : (
              <button
                key={s}
                type="button"
                className="wf-signal"
                data-testid={`wf-signal-${s}`}
                disabled={posting !== null}
                onClick={() => onSignal(s)}
              >
                {signalLabel(s)}
              </button>
            ),
          )}
          {canCancel ? (
            <button
              type="button"
              className="wf-signal wf-cancel"
              data-testid="wf-cancel"
              disabled={posting !== null}
              onClick={onCancelClick}
            >
              Cancel run
            </button>
          ) : null}
          {error ? (
            <span className="wf-signal-error" data-testid="wf-signal-error">
              {error.detail ?? error.title}
            </span>
          ) : null}
        </div>
      )}
    </div>
  );
}

/** `plan_stale`'s own body: the reason (byte-identical to the banner's own text — both read
 * `alert.reason`), the note that stands in for the line-diff this story does not add an
 * endpoint for, and the pre-filled `start a new run` link the brief's own binding rule asks
 * for beside `Continue`/`Cancel run` (rendered by the caller's own button row). */
function PlanStaleBody({ detail }: { detail: RunDetailOut }) {
  const run = detail.run;
  const params = new URLSearchParams({
    template: run.template,
    project: run.project,
    repository: run.repository,
    branch: run.branch,
  });
  return (
    <>
      <p className="wf-stop-reason">{bannerText(detail)}</p>
      <p className="wf-stop-reason">{PLAN_STALE_NOTE}</p>
      <p>
        <a className="wf-new-run-link" href={`/workflows/new?${params.toString()}`}>
          start a new run
        </a>
      </p>
    </>
  );
}
