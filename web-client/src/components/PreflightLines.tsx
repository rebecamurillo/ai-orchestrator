/**
 * The pre-flight readout (4.13, FR-8): `{status word} · {check} · {text}`, one line per
 * check, in the order the response gave them. Stateless — every prop is what to draw, never
 * how to get it — so it renders with `renderToStaticMarkup` and needs no DOM
 * (`web-client/AGENTS.md`).
 *
 * Only the `x` word is red (`data-signal="failed"` on the word alone, never the row): `!` is
 * plain text, exactly as the binding rules ask, so a warning never reads as a stop.
 */
import type { components } from '../api/schema';
import { checkSlug, lineWord } from '../lib/newwf/state';

type LineOut = components['schemas']['LineOut'];

interface Props {
  lines: LineOut[];
}

export default function PreflightLines({ lines }: Props) {
  return (
    <div className="newwf-preflight" data-testid="newwf-preflight">
      {lines.map((line) => (
        <p
          key={line.check}
          className="newwf-preflight-line"
          data-testid={`newwf-preflight-${checkSlug(line.check)}`}
        >
          <span className="newwf-preflight-row">
            <span
              className="newwf-preflight-word"
              data-signal={line.status === 'fail' ? 'failed' : undefined}
            >
              {lineWord(line.status)}
            </span>
            {' · '}
            {line.check}
            {' · '}
            {line.text}
          </span>
          {line.status === 'fail' && line.fix ? (
            <span className="newwf-preflight-fix">{line.fix}</span>
          ) : null}
        </p>
      ))}
    </div>
  );
}
