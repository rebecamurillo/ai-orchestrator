/**
 * The HISTORY section's dense table (7.5, SPEC CAP-5, UX-DR14): `time · project · workflow ·
 * path · kind · harness · status · time · cost · trace`, one row per attempt, newest first
 * with the currently-executing rows promoted (`promoted`, `lib/runs/history.ts`).
 *
 * Signal rule (NFR-6, binding rule): the status token is the **only** coloured cell in a
 * row. Every other cell is a plain string, and `SKP`/`unvalidated` stay words — `tokenSignal`
 * maps `SKP` to `neutral`, which is what keeps a skipped attempt off the signal hues.
 *
 * The whole row is the link target (binding rule: "rows link to `/workflows/{run_id}#step-
 * {seq}`"), carried on the `path` cell's anchor and repeated on the `workflow` cell so the
 * two things an Operator reaches for both reach it. The `trace` cell is the one link that
 * leaves this product.
 *
 * Stateless (`renderToStaticMarkup`), the `QueueTable.tsx`/`StepsTable.tsx` precedent.
 */
import { tokenSignal } from '../../lib/board/format';
import {
  costText,
  durationText,
  EMPTY_CELL,
  harnessText,
  HISTORY_COLUMNS,
  isCurrent,
  promoted,
  rowHref,
  startedText,
  TRACE_LINK_TEXT,
  workflowText,
  type HistoryRowOut,
} from '../../lib/runs/history';

interface Props {
  rows: HistoryRowOut[];
}

export default function HistoryTable({ rows }: Props) {
  return (
    <div className="runs-history-scroll">
      <table className="runs-history-table">
        <thead>
          <tr>
            {HISTORY_COLUMNS.map((column, at) => (
              <th key={`${column}-${at}`} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {promoted(rows).map((row) => (
            <tr
              key={row.attempt_id}
              data-testid={`runs-history-row-${row.attempt_id}`}
              data-current={isCurrent(row)}
            >
              <td>{startedText(row)}</td>
              <td>{row.project_name}</td>
              <td>
                <a href={rowHref(row)}>{workflowText(row)}</a>
              </td>
              <td>
                <a href={rowHref(row)}>{row.path}</a>
              </td>
              <td>{row.kind}</td>
              <td>{harnessText(row)}</td>
              <td>
                <span className="runs-history-token" data-signal={tokenSignal(row.token)}>
                  {row.token}
                </span>
              </td>
              <td>{durationText(row)}</td>
              <td>{costText(row)}</td>
              <td>
                {row.trace_url ? (
                  <a href={row.trace_url} rel="noreferrer noopener" target="_blank">
                    {TRACE_LINK_TEXT}
                  </a>
                ) : (
                  EMPTY_CELL
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
