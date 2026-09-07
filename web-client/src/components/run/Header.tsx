/**
 * The Run detail's header (4.15, UX-DR9): the crumb, the chip+token+branch+age line, the
 * unabridged meta line, and the `DIAGRAM · DETAIL` toggle — `DIAGRAM` stays disabled until
 * the run-graph screen (Epic 8) exists to switch to.
 *
 * Stateless — every prop is what to draw, `now` included, so age is deterministic under
 * `renderToStaticMarkup` rather than reading `Date.now()` itself (`RunCard.tsx`'s own
 * precedent for a value the caller already had to compute).
 */
import type { RunDetailOut, Token } from '../../lib/run/detail';
import { crumbText, metaLine, stateAgeSeconds } from '../../lib/run/detail';
import { ageText, tokenSignal } from '../../lib/board/format';

interface Props {
  detail: RunDetailOut;
  token: Token;
  now: number;
}

export default function Header({ detail, token, now }: Props) {
  const signal = tokenSignal(token);
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
      </p>
      <p className="wf-meta" data-testid="wf-meta">
        {metaLine(detail)}
      </p>
      <div className="wf-toggle" data-testid="wf-toggle-diagram">
        <span aria-disabled="true">DIAGRAM</span>
        <span aria-current="true">DETAIL</span>
      </div>
    </header>
  );
}
