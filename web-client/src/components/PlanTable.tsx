/**
 * *What will run* (4.13, AD-7: the same rows `create_run` would persist). A dense
 * `path · kind · gate` table, or the one red `plan error · …` line when the plan could not
 * be built — never both. Stateless, so it renders with `renderToStaticMarkup`
 * (`web-client/AGENTS.md`).
 *
 * A `skipped` row never turns its gate cell green: `{gate}` is replaced outright by
 * `skipped · {reason}`, in the same plain text as every other cell.
 */
import type { components } from '../api/schema';

type PlannedRowOut = components['schemas']['PlannedRowOut'];
type PlanErrorOut = components['schemas']['PlanErrorOut'];

interface Props {
  rows: PlannedRowOut[] | null;
  planError: PlanErrorOut | null;
}

function gateCell(row: PlannedRowOut): string {
  if (row.status !== 'skipped') return row.gate;
  // `reason` is nullable, and `skipped · ` with nothing after it reads as a missing value
  return row.reason ? `skipped · ${row.reason}` : 'skipped';
}

export default function PlanTable({ rows, planError }: Props) {
  if (planError) {
    const version = planError.version ?? '?';
    return (
      <p className="newwf-plan-error" data-testid="newwf-plan" data-signal="failed">
        plan error · {planError.template ?? '?'}@{version} · line {planError.line ?? '?'} ·{' '}
        {planError.reason}
      </p>
    );
  }

  return (
    <div className="newwf-plan-scroll">
      <table className="newwf-plan" data-testid="newwf-plan">
        <thead>
          <tr>
            <th scope="col">PATH</th>
            <th scope="col">KIND</th>
            <th scope="col">GATE</th>
          </tr>
        </thead>
        <tbody>
          {(rows ?? []).map((row) => (
            <tr key={row.seq} data-testid={`newwf-plan-row-${row.seq}`}>
              <td>{row.path}</td>
              <td>{row.kind}</td>
              <td>{gateCell(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
