/**
 * The Run detail's header (4.15, UX-DR9): the crumb, the chip+token+branch+age line and the
 * unabridged meta line.
 *
 * The `DIAGRAM · DETAIL` toggle is gone (EXPERIENCE-v1 delta 21, 2026-09-24): `?view=diagram`
 * was retired in 2026-09-15 and its redirect deleted with this rework, so the control linked
 * to a page that redirected to itself — chrome stating a choice that does not exist. The
 * `view` prop went with it; there is one Run detail and the diagram is part of it.
 *
 * The title is the Run's label (`RunTitle` edits it); the branch leads the meta line. `actions`
 * is the island's slot for controls that need state it owns (`RecalculateControl`).
 *
 * Every prop is what to draw, `now` included, so age is deterministic under
 * `renderToStaticMarkup` rather than reading `Date.now()` itself (`RunCard.tsx`'s own
 * precedent for a value the caller already had to compute).
 */
import type { ReactNode } from 'react';

import type { components } from '../../api/schema';
import type { RunDetailOut, Token } from '../../lib/run/detail';
import { crumbText, metaLine, stateAgeSeconds } from '../../lib/run/detail';
import { ageText, tokenSignal } from '../../lib/board/format';
import { runTitle } from '../../lib/run/label';
import RunTitle from './RunTitle';

type ProblemDetail = components['schemas']['ProblemDetail'];

interface Props {
  detail: RunDetailOut;
  token: Token;
  now: number;
  onSaveLabel?: (label: string | null) => Promise<ProblemDetail | null>;
  actions?: ReactNode;
}

const NO_SAVE = async (): Promise<ProblemDetail | null> => null;

export default function Header({ detail, token, now, onSaveLabel, actions }: Props) {
  const signal = tokenSignal(token);
  return (
    <header className="wf-header" data-testid="wf-header">
      <p className="wf-crumb">{crumbText(detail)}</p>
      <div className="wf-headline">
        <span className="wf-token" data-testid="wf-token" data-signal={signal}>
          <span className="wf-token-chip" />
          <span>{token}</span>
        </span>
        <RunTitle
          label={runTitle(detail.run)}
          byOperator={detail.run.label_set_by_operator ?? false}
          onSave={onSaveLabel ?? NO_SAVE}
        />
        <span className="wf-age">{ageText(stateAgeSeconds(detail, now))}</span>
      </div>
      <p className="wf-meta" data-testid="wf-meta">
        <span className="wf-meta-branch">{detail.run.branch}</span>
        {' · '}
        {metaLine(detail)}
      </p>
      {actions ? <div className="wf-header-actions">{actions}</div> : null}
    </header>
  );
}
