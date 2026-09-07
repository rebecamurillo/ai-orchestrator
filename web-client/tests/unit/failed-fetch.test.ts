/**
 * `FailedFetch.tsx` (4.14, UX-DR4): the full-surface failed-fetch readout. Stateless, so it
 * renders outright with `renderToStaticMarkup`; the retry click itself is proven in
 * `tests/e2e/board.spec.ts`, in a real browser.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import FailedFetch from '../../src/components/FailedFetch';

function render(status: number | null): string {
  return renderToStaticMarkup(
    createElement(FailedFetch, {
      method: 'GET',
      path: '/api/runs?view=board',
      status,
      onRetry: () => {},
    }),
  );
}

describe('FailedFetch', () => {
  it('carries the fetch-failed and fetch-retry testids', () => {
    const markup = render(500);
    expect(markup).toContain('data-testid="fetch-failed"');
    expect(markup).toContain('data-testid="fetch-retry"');
  });

  it('shows {method} {path} → {status} on an HTTP error', () => {
    expect(render(500)).toContain('GET /api/runs?view=board → 500');
  });

  it('shows "network error" when there is no status at all', () => {
    expect(render(null)).toContain('GET /api/runs?view=board → network error');
  });

  it('states the fact plainly, never an apology (NFR-8)', () => {
    const markup = render(500).toLowerCase();
    expect(markup).not.toContain('sorry');
    expect(markup).not.toContain('oops');
  });
});
