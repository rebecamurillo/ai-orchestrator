/**
 * One repository's section of the initiative detail screen (S7): the repository, its
 * integration branch, and every epic it holds paired with that epic's own merge Run
 * (`repoGroups`/`EpicPairing` — `src/lib/initiative/view.ts`'s own doc explains the pairing).
 *
 * Stateless (`renderToStaticMarkup`), `RunCard.tsx`'s own precedent.
 */
import MemberRow from './MemberRow';
import type { InitiativeMemberOut, RepoGroup } from '../../lib/initiative/view';

interface Props {
  group: RepoGroup;
  members: InitiativeMemberOut[];
}

export default function RepoSection({ group, members }: Props) {
  return (
    <div className="newin-detail-repo" data-testid={`newin-detail-repo-${group.repositoryId}`}>
      <p className="newin-detail-repo-head">
        {group.repository} · integration branch {group.branch ?? '—'} · default{' '}
        {group.defaultBranch}
      </p>
      {group.pairs.length === 0 ? (
        <p className="newin-empty">no epic in this repository</p>
      ) : (
        group.pairs.map((pair) => (
          <div
            className="newin-detail-pair"
            key={pair.epicId}
            data-testid={`newin-detail-pair-${pair.epicId}`}
          >
            <p className="newin-detail-epic-id">{pair.epicId}</p>
            {pair.epic ? (
              <MemberRow member={pair.epic} members={members} />
            ) : (
              <p className="newin-empty">no epic Run</p>
            )}
            {pair.merge ? (
              <MemberRow member={pair.merge} members={members} />
            ) : (
              <p className="newin-empty">no merge Run</p>
            )}
          </div>
        ))
      )}
    </div>
  );
}
