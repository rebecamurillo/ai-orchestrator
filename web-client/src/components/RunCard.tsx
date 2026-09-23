/**
 * One Board card (SPEC CAP-14): chip + token, branch, project, repository, the current or
 * last step's label, progress, `{template} v{version}`, age — the binding rule's fixed
 * field order, never reordered per Run.
 *
 * Stateless and DOM-free to unit-test (`renderToStaticMarkup`): every input is `CardOut`
 * itself plus `now` isn't needed (`age_seconds` already accounts for it server-side).
 *
 * The chip+token here is not `StatusToken.astro` (React cannot import a `.astro` component)
 * — `src/lib/board/format.ts::tokenSignal` is the same three-hue mapping that component
 * carries, duplicated rather than derived, same as `StatusToken.astro`'s own module doc
 * documents for its `SIGNALS` table.
 */
import type { components } from '../api/schema';
import {
  ageText,
  hasLeftRule,
  isAgedNeedsYou,
  progressText,
  tokenSignal,
} from '../lib/board/format';
import { initiativeBadgeText } from '../lib/initiative/badge';

type CardOut = components['schemas']['CardOut'];

interface Props {
  card: CardOut;
}

export default function RunCard({ card }: Props) {
  const signal = tokenSignal(card.token);
  const aged = isAgedNeedsYou(card.token, card.age_seconds);
  const progress = progressText(card.progress, card.kind_label);
  const badge = initiativeBadgeText(card);

  return (
    <a
      className="run-card"
      data-testid={`board-card-${card.id}`}
      data-left-rule={hasLeftRule(card.token) ? signal : undefined}
      href={`/workflows/${card.id}`}
    >
      <p className="run-card-head">
        <span className="run-card-token" data-signal={signal}>
          <span className="run-card-chip" />
          <span className="run-card-token-word">{card.token}</span>
        </span>
        {card.harness ? <span className="run-card-harness">{card.harness}</span> : null}
      </p>
      <p className="run-card-branch">{card.branch}</p>
      <p className="run-card-meta">
        {card.project_name} · {card.repository_slug}
      </p>
      {badge ? <p className="run-card-initiative">{badge}</p> : null}
      <p className="run-card-step">
        {card.current_step_label}
        {card.status === 'cancelled' ? ' · cancelled' : ''}
      </p>
      <p className="run-card-progress">{progress}</p>
      <p className="run-card-foot">
        <span className="run-card-template">
          {card.template} v{card.version}
        </span>
        <span className="run-card-age" data-signal={aged ? 'needs-you' : undefined}>
          {ageText(card.age_seconds)}
        </span>
      </p>
    </a>
  );
}
