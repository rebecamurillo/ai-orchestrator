/**
 * The pre-flight's per-repository table (S7): `repository · integration branch · branch
 * state`, one row per `InitiativeRepoOut`, in the order `POST /initiatives/preflight` already
 * returns them. A default-branch conflict is never detected here — it arrives as a `fail`
 * line in the pre-flight's own global `lines[]`, which `NewInitiative.tsx` renders through
 * `PreflightLines.tsx` beside this table, never through a colour on a cell of it.
 *
 * Stateless (`renderToStaticMarkup`), `PlanTable.tsx`'s own precedent.
 */
import type { components } from '../../api/schema';
import { branchStateText } from '../../lib/initiative/preflight';

type InitiativeRepoOut = components['schemas']['InitiativeRepoOut'];

interface Props {
  repos: InitiativeRepoOut[];
}

export default function RepoTable({ repos }: Props) {
  if (repos.length === 0) {
    return (
      <p className="newin-empty" data-testid="newin-repos-empty">
        no repository resolved yet
      </p>
    );
  }
  return (
    <div className="newin-scroll">
      <table className="newin-table" data-testid="newin-repos">
        <thead>
          <tr>
            <th scope="col">REPOSITORY</th>
            <th scope="col">INTEGRATION BRANCH</th>
            <th scope="col">DEFAULT BRANCH</th>
            <th scope="col">BRANCH STATE</th>
          </tr>
        </thead>
        <tbody>
          {repos.map((repo) => (
            <tr key={repo.repository_id} data-testid={`newin-repo-${repo.repository_id}`}>
              <td>{repo.repository}</td>
              <td>{repo.branch}</td>
              <td>{repo.default_branch}</td>
              <td>{branchStateText(repo.remote_holds_branch)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
