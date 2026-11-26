/** The Initiative page header: crumb, status, state line, position, tags and the meta line. */
import type { ReactNode } from 'react';

import { tokenSignal } from '../../lib/board/format';
import { cancelledStateLine } from '../../lib/initiative/actions';
import {
  headerMetaLine,
  headerPositionLine,
  headerStateLine,
  statusTokenWord,
  type InitiativeDetail,
} from '../../lib/initiative/page';
import { stopStateLine } from '../../lib/initiative/stops';
import Tag from '../initiatives/Tag';

interface Props {
  detail: InitiativeDetail;
  actions?: ReactNode;
}

export default function InitiativeHeader({ detail, actions }: Props) {
  const { token } = statusTokenWord(detail.status);
  return (
    <header className="ini-header" data-testid="ini-header">
      <p className="ini-crumb">
        <a href="/initiatives">initiatives</a> / {detail.slug}
      </p>
      <div className="ini-header-main">
        <span className="ini-card-token" data-signal={tokenSignal(token)}>
          <span className="ini-card-chip" />
          {token}
        </span>
        <h1 className="ini-title">{detail.slug}</h1>
        <p className="ini-state">
          {detail.status === 'cancelled'
            ? cancelledStateLine(detail)
            : (stopStateLine(detail) ?? headerStateLine(detail))}
        </p>
        <p className="ini-position">{headerPositionLine(detail)}</p>
        {actions ? <div className="ini-actions">{actions}</div> : null}
      </div>
      <p className="ini-header-tags">
        <Tag label="project" value={detail.project_name} />
        {detail.repo_tag.map((repo) => (
          <Tag key={repo} label="repo" value={repo} />
        ))}
      </p>
      <p className="ini-meta">{headerMetaLine(detail)}</p>
    </header>
  );
}
