/**
 * The full-surface failed-fetch readout (UX-DR4, `web-client/AGENTS.md`'s "a failed fetch
 * renders the full-surface readout with the failed request and a retry control"). `Board.tsx`
 * (4.14) is the first caller; Run detail (4.15) reuses this component unchanged for its own
 * poll, which is why every prop is generic (`method`/`path`/`status`) rather than Board-
 * specific.
 *
 * Stateless and DOM-free to unit-test (`renderToStaticMarkup`, the `PreflightLines.tsx`
 * precedent): the caller owns retry-in-flight state and passes `onRetry`, never fetches here.
 *
 * Nothing about this component carries a signal colour — a failed *fetch* is not the red
 * `ERR` token (that means a Run failed); it is a plain, factual command line (NFR-8: states
 * facts, never apologises).
 */
import { fetchFailureMessage } from '../lib/board/format';

interface Props {
  method: string;
  path: string;
  status: number | null;
  onRetry: () => void;
}

export default function FailedFetch({ method, path, status, onRetry }: Props) {
  return (
    <section className="failed-fetch" data-testid="fetch-failed">
      <p className="failed-fetch-headline">COULD NOT REACH BACKEND-API</p>
      <figure className="failed-fetch-block">
        <figcaption className="failed-fetch-eyebrow">REQUEST</figcaption>
        <pre className="failed-fetch-command">{fetchFailureMessage(method, path, status)}</pre>
      </figure>
      <button
        type="button"
        className="failed-fetch-retry"
        data-testid="fetch-retry"
        onClick={onRetry}
      >
        Retry
      </button>
    </section>
  );
}
