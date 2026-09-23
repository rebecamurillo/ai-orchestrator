/**
 * One member Run on the initiative detail screen (S7): its own token, role, branch (linking
 * to `/workflows/{run_id}`), a park readout when parked, and the "waits for" edge line.
 *
 * The token is `Header.tsx`'s own chip+word markup, duplicated the way that module's own
 * `RunCard.tsx`/`StatusToken.astro` precedent already duplicates a three-hue signal map
 * across the React/Astro boundary — `InitiativeMemberOut` carries `status`/`park_kind` as
 * two flat fields with no `RunDetailOut`-shaped `run`/`alert` to hand `Header.tsx` instead.
 *
 * Stateless (`renderToStaticMarkup`), `RunCard.tsx`'s own precedent.
 */
import { tokenSignal } from '../../lib/board/format';
import {
  memberHref,
  memberToken,
  waitsForText,
  type InitiativeMemberOut,
} from '../../lib/initiative/view';

interface Props {
  member: InitiativeMemberOut;
  members: InitiativeMemberOut[];
}

export default function MemberRow({ member, members }: Props) {
  const token = memberToken(member.status, member.park_kind);
  const signal = tokenSignal(token);
  const waits = waitsForText(member, members);

  return (
    <div className="newin-member" data-testid={`newin-member-${member.run_id}`}>
      <p className="newin-member-head">
        <span className="newin-member-token" data-signal={signal}>
          <span className="newin-member-chip" />
          <span>{token}</span>
        </span>
        <span className="newin-member-role">{member.role ?? '—'}</span>
        <a className="newin-member-link" href={memberHref(member.run_id)}>
          {member.branch}
        </a>
      </p>
      {member.park_kind ? (
        <p className="newin-member-park" data-testid={`newin-member-${member.run_id}-park`}>
          {member.park_kind}
          {member.park_reason ? ` · ${member.park_reason}` : ''}
        </p>
      ) : null}
      {waits ? <p className="newin-member-waits">{waits}</p> : null}
    </div>
  );
}
