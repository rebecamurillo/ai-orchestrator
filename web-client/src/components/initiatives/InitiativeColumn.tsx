/** One board column: head, count line, cards (or `—`). The DONE column passes no type and no count line. */
import type { ReactNode } from 'react';

import {
  columnCountText,
  columnHeadName,
  columnTypeWord,
  type InitiativeRow,
} from '../../lib/initiatives/format';
import InitiativeCard from './InitiativeCard';

interface Props {
  testId: string;
  /** A workflow name (shown upper-case) or, for DONE, the finished head text. */
  name: string;
  type?: string;
  items: InitiativeRow[];
  nowMs: number;
  footer?: ReactNode;
}

export default function InitiativeColumn({ testId, name, type, items, nowMs, footer }: Props) {
  const counts =
    type === undefined
      ? null
      : columnCountText(items.length, items.filter((i) => i.status === 'waiting for her').length);
  return (
    <section className="ini-column" data-testid={testId}>
      <header className="ini-column-head">
        <span className="ini-column-title">
          <span>{type === undefined ? name : columnHeadName(name)}</span>
          {type !== undefined && <span className="ini-column-type">{columnTypeWord(type)}</span>}
        </span>
        {counts && (
          <span className="ini-column-counts">
            {counts.ongoing}
            {counts.needYou && (
              <>
                {' · '}
                <span data-signal="needs-you">{counts.needYou}</span>
              </>
            )}
          </span>
        )}
      </header>
      <div className="ini-column-body">
        {items.length === 0 ? (
          <span className="ini-column-empty">—</span>
        ) : (
          items.map((item) => <InitiativeCard key={item.id} item={item} nowMs={nowMs} />)
        )}
        {footer}
      </div>
    </section>
  );
}
