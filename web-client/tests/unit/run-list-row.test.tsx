/**
 * `RunListRow.tsx` (story 8-4): a flat list row for the Board list view. Stateless and
 * DOM-free — uses `renderToStaticMarkup` + `createElement`, the same pattern `RunCard.tsx`'s
 * own unit test establishes. `.tsx` extension so the file type matches the component's.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RunListRow from '../../src/components/RunListRow';
import type { components } from '../../src/api/schema';

type CardOut = components['schemas']['CardOut'];

function card(overrides: Partial<CardOut> = {}): CardOut {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    token: 'RUN',
    status: 'running',
    park_kind: null,
    branch: 'epics/1',
    project_name: 'demo',
    repository_slug: 'demo-repo',
    current_step_label: 'epic 1 · story 3-2 · build',
    harness: null,
    template: 'initiative',
    version: 1,
    progress: { epics_done: 1, epics_total: 2, stories_done: 5, stories_total: 8, links: 1 },
    kind_label: null,
    age_seconds: 60,
    needs_you_since: null,
    ...overrides,
  };
}

function render(overrides: Partial<CardOut> = {}): string {
  return renderToStaticMarkup(createElement(RunListRow, { card: card(overrides) }));
}

describe('RunListRow', () => {
  it('links to the run detail page with the correct testid and href', () => {
    const markup = render({ id: 'run-abc' });
    expect(markup).toContain('data-testid="board-list-row-run-abc"');
    expect(markup).toContain('href="/workflows/run-abc"');
  });

  it('renders all 7 text fields: token, project, repo, branch, step, progress, age', () => {
    const markup = render();
    expect(markup).toContain('RUN');
    expect(markup).toContain('demo');
    expect(markup).toContain('demo-repo');
    expect(markup).toContain('epics/1');
    expect(markup).toContain('epic 1 · story 3-2 · build');
    expect(markup).toContain('1/2 epics');
    expect(markup).toContain('1m');
  });

  it('non-aged RUN card: token cell carries data-signal="run", age cell has no data-signal', () => {
    const markup = render({ token: 'RUN', age_seconds: 60 });
    // token cell
    expect(markup).toContain('class="board-list-token" data-signal="run"');
    // age cell — must not have data-signal
    const ageSpan = /<span class="board-list-age"[^>]*>/.exec(markup);
    expect(ageSpan?.[0]).not.toContain('data-signal');
  });

  it('BLK card aged >48h: token cell and age cell both carry data-signal="needs-you"', () => {
    const markup = render({ token: 'BLK', status: 'needs_you', age_seconds: 49 * 3600 });
    expect(markup).toContain('class="board-list-token" data-signal="needs-you"');
    const ageSpan = /<span class="board-list-age"[^>]*>/.exec(markup);
    expect(ageSpan?.[0]).toContain('data-signal="needs-you"');
  });

  it('CHK card (young, <48h): token carries data-signal="needs-you" (tokenSignal), age cell has no data-signal', () => {
    const markup = render({ token: 'CHK', status: 'needs_you', age_seconds: 3600 });
    // CHK maps to needs-you via tokenSignal, but isAgedNeedsYou is false (age < threshold)
    expect(markup).toContain('class="board-list-token" data-signal="needs-you"');
    const ageSpan = /<span class="board-list-age"[^>]*>/.exec(markup);
    expect(ageSpan?.[0]).not.toContain('data-signal');
  });

  // `renders the initiative badge when the row is a member (S8)` and `omits the
  // initiative badge for a Run started on its own` were here: Operator decision
  // 2026-09-30 removed the fan-in Initiative feature entirely, and `CardOut` no longer
  // carries `initiative`/`initiative_role`, so `RunListRow` renders no badge.
});
