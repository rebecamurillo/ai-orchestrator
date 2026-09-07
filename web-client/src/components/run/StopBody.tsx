/**
 * The stop body (4.15, UX-DR10): what stopped the Run, in words and — where the park kind
 * has one — a log tail, then the buttons `admitted_signals` and this epic's own effects
 * (`cancel`, `retry`, `continue` — SPEC Non-goals) both allow. `park_kind`-keyed rather than
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
  currentStepPath,
  logTail,
  stepAt,
  stopKind,
  stopSignals,
} from '../../lib/run/detail';
import { signalLabel, type SignalKind } from '../../lib/run/signals';

type ProblemDetail = components['schemas']['ProblemDetail'];

interface Props {
  detail: RunDetailOut;
  token: Token;
  onSignal: (kind: SignalKind) => void;
  onCancelClick: () => void;
  posting: SignalKind | null;
  error: ProblemDetail | null;
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
}: Props) {
  const kind = stopKind(detail, token);
  if (kind === null) return null;

  const signals = stopSignals(detail.admitted_signals);
  const canCancel = detail.admitted_signals.includes('cancel');
  const tail = logTail(detail);
  const path = currentStepPath(detail);
  const row = stepAt(detail.steps, path);

  return (
    <div className="wf-stop" data-testid={`wf-stop-${kind}`}>
      {kind === 'plan_stale' ? <PlanStaleBody detail={detail} /> : null}
      {kind === 'push_rejected' ? <p className="wf-stop-reason">{RESOLVE_LINE}</p> : null}
      {kind === 'checkpoint' ? <p className="wf-stop-reason">{bannerText(detail)}</p> : null}
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
          {signals.map((s) => (
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
          ))}
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
