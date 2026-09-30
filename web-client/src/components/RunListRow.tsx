/**
 * One row in the Board list view (story 8-4): the same seven fields as a board card but in
 * a flat, compact row instead of a stacked card. Stateless and DOM-free to unit-test
 * (`renderToStaticMarkup`), the same constraint `RunCard.tsx` documents for itself.
 *
 * Signal rule identical to the card: `isAgedNeedsYou` sets `data-signal="needs-you"` on the
 * token cell and age cell only; nothing else in the row carries a signal colour.
 */
import type { components } from '../api/schema';
import { ageText, isAgedNeedsYou, progressText, tokenSignal } from '../lib/board/format';

type CardOut = components['schemas']['CardOut'];

interface Props {
  card: CardOut;
}

export default function RunListRow({ card }: Props) {
  const signal = tokenSignal(card.token);
  const aged = isAgedNeedsYou(card.token, card.age_seconds);
  const progress = progressText(card.progress, card.kind_label);

  return (
    <a
      className="board-list-row"
      data-testid={`board-list-row-${card.id}`}
      href={`/workflows/${card.id}`}
    >
      <span className="board-list-token" data-signal={aged ? 'needs-you' : signal}>
        <span className="board-list-chip" aria-hidden="true" />
        {card.token}
      </span>
      <span className="board-list-project">{card.project_name}</span>
      <span className="board-list-repo">{card.repository_slug}</span>
      <span className="board-list-branch">{card.branch}</span>
      <span className="board-list-step">{card.current_step_label}</span>
      <span className="board-list-progress">{progress}</span>
      <span className="board-list-age" data-signal={aged ? 'needs-you' : undefined}>
        {ageText(card.age_seconds)}
      </span>
    </a>
  );
}
