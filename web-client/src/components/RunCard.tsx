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
import Tag from './initiatives/Tag';
import '../styles/initiatives.css';
import {
  ageText,
  cardHref,
  cardStepText,
  cardTypeText,
  hasLeftRule,
  isAgedNeedsYou,
  progressText,
  tokenSignal,
} from '../lib/board/format';

type CardOut = components['schemas']['CardOut'];

interface Props {
  card: CardOut;
}

export default function RunCard({ card }: Props) {
  const signal = tokenSignal(card.token);
  const aged = isAgedNeedsYou(card.token, card.age_seconds);
  const progress = progressText(card.progress, card.kind_label);

  return (
    <article
      className="run-card"
      data-testid={`board-card-${card.id}`}
      data-left-rule={hasLeftRule(card.token) ? signal : undefined}
    >
      <p className="run-card-head">
        <span className="run-card-token" data-signal={signal}>
          <span className="run-card-chip" />
          <span className="run-card-token-word">{card.token}</span>
        </span>
        <span className="run-card-type">{cardTypeText(card.template_type, card.harness)}</span>
      </p>
      <p className="run-card-branch">
        <a className="run-card-link" href={cardHref(card)}>
          {card.branch}
        </a>
      </p>
      {card.initiative ? (
        <p className="run-card-tag">
          <Tag
            label="initiative"
            value={card.initiative.slug}
            href={`/initiatives/${card.initiative.id}`}
            testId="board-initiative-tag"
          />
        </p>
      ) : null}
      <p className="run-card-meta">
        {card.project_name} · {card.repository_slug}
      </p>
      <p className="run-card-step">{cardStepText(card)}</p>
      <p className="run-card-progress">{progress}</p>
      <p className="run-card-foot">
        <span className="run-card-template">
          {card.template} v{card.version}
        </span>
        <span className="run-card-age" data-signal={aged ? 'needs-you' : undefined}>
          {ageText(card.age_seconds)}
        </span>
      </p>
    </article>
  );
}
