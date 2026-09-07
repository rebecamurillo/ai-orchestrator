/**
 * The Steps table (4.15, UX-DR16): `path · kind · gate · status · time · harness · cost`,
 * every planned row from `steps[]`, visible from the start (the brief's own acceptance).
 *
 * The only coloured cell is the status token (NFR-6) — `tokenSignal` is `board/format.ts`'s
 * own three-hue map, reused rather than redefined so a card and a step row never disagree on
 * what a token means. `gate` and `SKP`/`unvalidated` stay plain words (binding rule).
 *
 * Stateless (`renderToStaticMarkup`).
 */
import type { RunDetailOut, StepRowOut } from '../../lib/run/detail';
import { currentStepPath, stepStatusText } from '../../lib/run/detail';
import { ageText, tokenSignal } from '../../lib/board/format';

interface Props {
  detail: RunDetailOut;
}

const COLUMNS = ['path', 'kind', 'gate', 'status', 'time', 'harness', 'cost'];

function timeText(step: StepRowOut): string {
  const seconds = step.latest?.seconds;
  return seconds == null ? '—' : ageText(seconds);
}

function costText(step: StepRowOut): string {
  const cost = step.latest?.cost_usd;
  return cost == null ? '—' : `$${cost}`;
}

function attemptsSuffix(step: StepRowOut): string {
  return step.attempts > 1 ? ` · ${step.attempts} attempts` : '';
}

export default function StepsTable({ detail }: Props) {
  const current = currentStepPath(detail);
  return (
    <div className="wf-steps-scroll">
      <table className="wf-steps" data-testid="wf-steps">
        <thead>
          <tr>
            {COLUMNS.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {detail.steps.map((step) => (
            <tr
              key={step.seq}
              data-testid={`wf-step-${step.seq}`}
              data-current={step.path === current}
            >
              <td>{step.path}</td>
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
          ))}
        </tbody>
      </table>
    </div>
  );
}
