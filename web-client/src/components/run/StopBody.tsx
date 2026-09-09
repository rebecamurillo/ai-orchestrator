/**
 * The stop body (4.15, UX-DR10): what stopped the Run, in words and — where the park kind
 * has one — a log tail, then the buttons `admitted_signals` and the effects that have landed
 * (`cancel`, `retry`, `continue`; `answer` 6.1, `skip_story` 6.4) both allow.
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
import { answerTarget, offersAnswer } from '../../lib/run/answer';
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
  SKIP_STORY_LABEL,
  offersSkipStory,
  skipStoryConfirmLine,
} from '../../lib/run/skip';
import AnswerBox from './AnswerBox';
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
  const signals =
    offersSkipStory(kind, detail.admitted_signals, skipStoryId) && !offered.includes('skip_story')
      ? [...offered, 'skip_story' as SignalKind]
      : offered;
  const skipStoryLine = skipStoryConfirmLine(skipStoryId);
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
          {signals.map((s) =>
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
