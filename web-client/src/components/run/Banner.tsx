/**
 * The banner area (4.15, UX-DR9): the Alert banner for `needs_you`/`failed`, the grey
 * `cancelled by operator at {time}` line for `cancelled`, the `done` summary line, and
 * nothing at all for `running`/`queued` — "Other states" in the brief's own binding rules.
 *
 * Stateless (`renderToStaticMarkup`, `RunCard.tsx`'s own precedent). `bannerLevel` is the
 * only thing that ever colours this component's left rule — `SKP`/other tokens never reach
 * it (NFR-6: "a screen with nothing needing the operator has no amber or red pixel").
 */
import type { RunDetailOut, Token } from '../../lib/run/detail';
import {
  bannerLevel,
  bannerText,
  cancelledAtText,
  moneyRatio,
  storiesProgressText,
  summaryLine,
} from '../../lib/run/detail';

interface Props {
  detail: RunDetailOut;
  token: Token;
}

export default function Banner({ detail, token }: Props) {
  const level = bannerLevel(token);

  if (level) {
    const progress = storiesProgressText(detail);
    // `blocked`'s own Question block (`QuestionBlock.tsx`) carries the amber left rule for
    // that park kind (5.10's own signal rule: the question block's rule and the current
    // strip cell are the only amber elements a `blocked` detail shows) — this banner stays
    // neutral rather than adding a second one.
    const signal = detail.alert?.park_kind === 'blocked' ? 'neutral' : level;
    return (
      <aside className="wf-alert" data-testid="wf-alert" data-signal={signal} role="status">
        <span>
          {token} · {bannerText(detail)}
        </span>
        <span className="wf-alert-side">
          {progress ? `${progress} · ` : ''}
          {moneyRatio(detail.cost)}
        </span>
      </aside>
    );
  }

  if (token === 'CAN') {
    return (
      <aside className="wf-alert" data-testid="wf-alert" data-signal="neutral" role="status">
        {cancelledAtText(detail)}
      </aside>
    );
  }

  if (token === 'DON') {
    return (
      <p className="wf-summary" data-testid="wf-summary">
        {summaryLine(detail)}
      </p>
    );
  }

  return null;
}
