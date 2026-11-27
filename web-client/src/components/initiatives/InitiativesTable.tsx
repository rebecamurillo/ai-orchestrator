/** The dense list of initiatives: status maps to its token, rows sort by last change, fields are joined. */
import { ageText, isAgedNeedsYou, tokenSignal } from '../../lib/board/format';
import {
  ageSecondsSince,
  byLastChange,
  statusToken,
  workflowCellText,
  type InitiativeRow,
} from '../../lib/initiatives/format';

interface Props {
  rows: InitiativeRow[];
  showProject: boolean;
}

export default function InitiativesTable({ rows, showProject }: Props) {
  const nowMs = Date.now();
  return (
    <table className="ini-table" data-testid="initiatives-list">
      <thead>
        <tr>
          <th>Status</th>
          {showProject ? <th>Project</th> : null}
          <th>Repository</th>
          <th>Initiative</th>
          <th>Workflow</th>
          <th>Current step</th>
          <th>Last change</th>
        </tr>
      </thead>
      <tbody>
        {byLastChange(rows).map((row) => {
          const { token } = statusToken(row.status);
          const age = ageSecondsSince(row.updated_at, nowMs);
          return (
            <tr key={row.id} data-testid={`initiatives-row-${row.slug}`}>
              <td>
                <span className="ini-table-token" data-signal={tokenSignal(token)}>
                  <span className="ini-card-chip" />
                  {token}
                </span>
              </td>
              {showProject ? <td className="ini-table-sub">{row.project_name}</td> : null}
              <td className="ini-table-sub">{row.repo_tag.join(', ')}</td>
              <td>
                <a href={`/initiatives/${row.id}`}>{row.name}</a>
              </td>
              <td className="ini-table-sub">{workflowCellText(row)}</td>
              <td data-signal={row.status === 'waiting for her' ? 'needs-you' : undefined}>
                {row.line}
              </td>
              <td
                className="ini-table-age"
                data-signal={isAgedNeedsYou(token, age) ? 'needs-you' : undefined}
              >
                {ageText(age)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
