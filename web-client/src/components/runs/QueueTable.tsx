/**
 * The QUEUE section's dense table (4.16, SPEC CAP-16, UX-DR14): `pos · project · workflow ·
 * next step · waiting because · waiting`, one row per `QueueItemOut`, in the order `GET
 * /queue` already returns them (`application/use_cases/queue.py::_order_key`'s own "active
 * first, then queued by position" — this table never re-sorts).
 *
 * Signal rule (binding rule): "no colour in this table ... keep the table token-free;
 * reasons are words" — every cell is a plain string; `reason` is `GET /queue`'s own fixed
 * sentence, printed verbatim, never reworded or mapped to friendlier copy (this story's own
 * operating rule).
 *
 * Stateless (`renderToStaticMarkup`), the `StepsTable.tsx` precedent.
 */
import { ageText } from '../../lib/board/format';
import {
  isParked,
  nextStepText,
  PARKED_HINT,
  positionText,
  projectCell,
  QUEUE_COLUMNS,
  workflowHref,
  workflowText,
  type QueueItemOut,
} from '../../lib/runs/queue';

interface Props {
  items: QueueItemOut[];
}

export default function QueueTable({ items }: Props) {
  return (
    <div className="runs-queue-scroll">
      <table className="runs-queue-table">
        <thead>
          <tr>
            {QUEUE_COLUMNS.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr key={row.run.id} data-testid={`runs-queue-row-${row.run.id}`}>
              <td>{positionText(row.position)}</td>
              <td>{projectCell(row.run)}</td>
              <td>
                <a href={workflowHref(row.run)}>{workflowText(row.run)}</a>
              </td>
              <td>{nextStepText(row)}</td>
              <td>
                {row.reason}
                {isParked(row) ? (
                  // an explicit text separator, not only the `display: block` in `runs.css`
                  // — the two sentences must still read apart with no stylesheet loaded
                  <>
                    {' · '}
                    <span className="runs-queue-hint">{PARKED_HINT}</span>
                  </>
                ) : null}
              </td>
              <td>{ageText(row.waiting_seconds)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
