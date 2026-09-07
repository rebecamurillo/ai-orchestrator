/**
 * One Board column (SPEC CAP-14, UX-DR7): header word + count, `—` when empty, else its
 * cards. Split out of `Board.tsx` so both stay well under `web-client/AGENTS.md`'s 300-line
 * component cap (the `NewWorkflowFields.tsx`/`NewWorkflow.tsx` split, 4.13, is the precedent)
 * and so it unit-tests with `renderToStaticMarkup` on its own.
 *
 * `cap` is only ever passed for `done`/`failed` — the bound 4.12 deferred to this story
 * (Design Notes): `queued`/`running`/`needs_you` are never capped, so `cap` stays `undefined`
 * for those three and every card renders.
 */
import type { components } from '../api/schema';
import { capColumn, moreNotShownText } from '../lib/board/format';
import RunCard from './RunCard';

type CardOut = components['schemas']['CardOut'];
type Status = 'queued' | 'running' | 'needs_you' | 'done' | 'failed';

interface Props {
  status: Status;
  label: string;
  cards: CardOut[];
  cap?: number;
}

/** The Running header is green, the Needs-you header amber only when its own count is
 * greater than 0 (binding rule) — every other column head is plain. */
function headSignal(status: Status, count: number): 'run' | 'needs-you' | undefined {
  if (status === 'running') return 'run';
  if (status === 'needs_you' && count > 0) return 'needs-you';
  return undefined;
}

export default function BoardColumn({ status, label, cards, cap }: Props) {
  const { shown, more } = cap === undefined ? { shown: cards, more: 0 } : capColumn(cards, cap);

  return (
    <section className="board-column" data-testid={`board-column-${status}`}>
      <header className="board-column-head" data-signal={headSignal(status, cards.length)}>
        <span className="board-column-label">{label}</span>
        <span className="board-column-count">{cards.length}</span>
      </header>
      <div className="board-column-body">
        {shown.length === 0 ? (
          <p className="board-column-empty">—</p>
        ) : (
          shown.map((card) => <RunCard key={card.id} card={card} />)
        )}
        {more > 0 ? <p className="board-column-more">{moreNotShownText(more)}</p> : null}
      </div>
    </section>
  );
}
