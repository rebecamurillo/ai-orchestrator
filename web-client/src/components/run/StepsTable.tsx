/**
 * The Steps table (4.15, UX-DR16): `path · kind · gate · status · time · harness · cost`,
 * every planned row from `steps[]`, visible from the start (the brief's own acceptance).
 *
 * The only coloured cell is the status token (NFR-6) — `tokenSignal` is `board/format.ts`'s
 * own three-hue map, reused rather than redefined so a card and a step row never disagree on
 * what a token means. `gate` and `SKP`/`unvalidated` stay plain words (binding rule).
 *
 * Every row carries `id="step-{seq}"` (7.5): that is the fragment a Runs history row links
 * to (`lib/run/anchor.ts`), and `anchoredSeq` is the row the Run detail scrolled to and
 * promotes briefly on arrival. `data-anchored` is a neutral promotion — the status token is
 * still the only signal-coloured cell in the row (NFR-6).
 *
 * Reads `$stepDrawer` for the selected row; a row's path opens the step drawer (epic 2 story 2).
 */
import { useStore } from '@nanostores/react';
import { Fragment } from 'react';
import type { RunDetailOut, StepRowOut } from '../../lib/run/detail';
import HintControl from '../metrics/HintControl';
import { currentStepPath, stepStatusText } from '../../lib/run/detail';
import { ageText, tokenSignal } from '../../lib/board/format';
import { stepAnchorId } from '../../lib/run/anchor';
import { $stepDrawer, openStepDrawer } from '../../stores/step-drawer';

interface Props {
  detail: RunDetailOut;
  anchoredSeq?: number | null;
  /** Still passed by callers; the path now opens the step drawer, which owns the page link. */
  runId?: string;
}

const COLUMNS = ['path', 'kind', 'gate', 'status', 'time', 'harness', 'cost'];

function timeText(step: StepRowOut): string {
  const seconds = step.latest?.seconds;
  return seconds == null ? '—' : ageText(seconds);
}

/** The row's own `cost_usd` (5.3, summed across every attempt) as `$0.00`, with the word
 * `provisional` after it when the latest attempt's own cost is still an estimate (5.10). */
function costText(step: StepRowOut): string {
  const provisional = step.latest?.cost_provisional ? ' provisional' : '';
  return `$${step.cost_usd ?? '0'}${provisional}`;
}

function attemptsSuffix(step: StepRowOut): string {
  return step.attempts > 1 ? ` · ${step.attempts} attempts` : '';
}

export default function StepsTable({ detail, anchoredSeq = null }: Props) {
  const open = useStore($stepDrawer);
  const current = currentStepPath(detail);
  return (
    <div className="wf-steps-scroll">
      <table className="wf-steps" data-testid="wf-steps">
        <thead>
          <tr>
            {COLUMNS.map((column) => (
              <th key={column} scope="col">
                {column}
                {column === 'cost' ? <HintControl metricId="spend.recorded" /> : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {detail.steps.map((step) => {
            const openerId = `wf-step-open-${step.seq}`;
            return (
              <Fragment key={step.seq}>
                <tr
                  id={stepAnchorId(step.seq)}
                  data-testid={`wf-step-${step.seq}`}
                  data-current={step.path === current}
                  data-anchored={step.seq === anchoredSeq}
                  className={open?.seq === step.seq ? 'wf-step-selected' : undefined}
                >
                  <td>
                    <button
                      type="button"
                      className="wf-step-open"
                      id={openerId}
                      onClick={() => openStepDrawer(step.seq, step.latest?.n ?? 0, openerId)}
                    >
                      {step.path}
                    </button>
                  </td>
                  <td>{step.kind}</td>
                  <td>{step.gate}</td>
                  <td>
                    <span className="wf-step-token" data-signal={tokenSignal(step.token)}>
                      {stepStatusText(step)}
                    </span>
                    {attemptsSuffix(step)}
                  </td>
                  <td>{timeText(step)}</td>
                  <td>{step.latest?.harness ?? '—'}</td>
                  <td>{costText(step)}</td>
                </tr>
                {step.retry_prompt ? (
                  <tr data-testid={`wf-step-${step.seq}-retry-prompt`}>
                    <td colSpan={COLUMNS.length}>{step.retry_prompt}</td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
