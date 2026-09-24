/**
 * The Run detail's header (4.15, UX-DR9): the crumb, the chip+token+branch+age line and the
 * unabridged meta line.
 *
 * The `DIAGRAM · DETAIL` toggle is gone (EXPERIENCE-v1 delta 21, 2026-09-24): `?view=diagram`
 * was retired in 2026-09-15 and its redirect deleted with this rework, so the control linked
 * to a page that redirected to itself — chrome stating a choice that does not exist. The
 * `view` prop went with it; there is one Run detail and the diagram is part of it.
 *
 * Stateless — every prop is what to draw, `now` included, so age is deterministic under
 * `renderToStaticMarkup` rather than reading `Date.now()` itself (`RunCard.tsx`'s own
 * precedent for a value the caller already had to compute).
 */
import type { RunDetailOut, Token } from '../../lib/run/detail';
import { crumbText, metaLine, stateAgeSeconds } from '../../lib/run/detail';
import { ageText, tokenSignal } from '../../lib/board/format';
import { initiativeBadgeText, initiativeHref } from '../../lib/initiative/badge';

interface Props {
  detail: RunDetailOut;
  token: Token;
  now: number;
}

export default function Header({ detail, token, now }: Props) {
  const signal = tokenSignal(token);
  const badge = initiativeBadgeText(detail.run);
  return (
    <header className="wf-header" data-testid="wf-header">
      <p className="wf-crumb">{crumbText(detail)}</p>
      <p className="wf-headline">
        <span className="wf-token" data-testid="wf-token" data-signal={signal}>
          <span className="wf-token-chip" />
          <span>{token}</span>
        </span>
        <span className="wf-branch">{detail.run.branch}</span>
        <span className="wf-age">{ageText(stateAgeSeconds(detail, now))}</span>
        {badge ? (
          <a
            className="wf-initiative"
            data-testid="wf-initiative"
            href={initiativeHref(detail.run.initiative ?? '')}
          >
            {badge}
          </a>
        ) : null}
      </p>
      <p className="wf-meta" data-testid="wf-meta">
        {metaLine(detail)}
      </p>
    </header>
  );
}
