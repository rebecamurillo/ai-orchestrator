/**
 * `BoardColumn.tsx` (4.14, SPEC CAP-14, UX-DR7): one column's header (word + count, green
 * for Running, amber for Needs you only when its count is > 0) and body (`—` when empty,
 * else cards, capped only when `cap` is passed).
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import BoardColumn from '../../src/components/BoardColumn';
import type { components } from '../../src/api/schema';

type CardOut = components['schemas']['CardOut'];

function card(overrides: Partial<CardOut> = {}): CardOut {
  return {
    id: `card-${Math.random()}`,
    token: 'DON',
    status: 'done',
    park_kind: null,
    branch: 'main',
    project_name: 'demo',
    repository_slug: 'demo-repo',
    current_step_label: 'link',
    harness: null,
    template: 'repo-init',
    version: 1,
    progress: null,
    kind_label: 'repo-init',
    age_seconds: 10,
    needs_you_since: null,
    ...overrides,
  };
}

describe('BoardColumn', () => {
  it('carries the board-column-<status> testid and the header count', () => {
    const markup = renderToStaticMarkup(
      createElement(BoardColumn, { status: 'queued', label: 'Queued', cards: [] }),
    );
    expect(markup).toContain('data-testid="board-column-queued"');
    expect(markup).toContain('>0<');
  });

  it('renders — for an empty column', () => {
    const markup = renderToStaticMarkup(
      createElement(BoardColumn, { status: 'done', label: 'Done', cards: [] }),
    );
    expect(markup).toContain('—');
  });

  it('colours the Running header green', () => {
    const markup = renderToStaticMarkup(
      createElement(BoardColumn, { status: 'running', label: 'Running', cards: [card()] }),
    );
    expect(markup).toContain('data-signal="run"');
  });

  it('colours the Needs you header amber only when its count is > 0', () => {
    const withCards = renderToStaticMarkup(
      createElement(BoardColumn, { status: 'needs_you', label: 'Needs you', cards: [card()] }),
    );
    const empty = renderToStaticMarkup(
      createElement(BoardColumn, { status: 'needs_you', label: 'Needs you', cards: [] }),
    );
    expect(withCards).toContain('data-signal="needs-you"');
    expect(empty).not.toContain('data-signal');
  });

  it('renders every card when no cap is given', () => {
    const cards = Array.from({ length: 25 }, () => card());
    const markup = renderToStaticMarkup(
      createElement(BoardColumn, { status: 'queued', label: 'Queued', cards }),
    );
    expect(markup.match(/board-card-/g)).toHaveLength(25);
    expect(markup).not.toContain('more not shown');
  });

  it('caps done/failed at the given size and states how many were left out', () => {
    const cards = Array.from({ length: 25 }, () => card());
    const markup = renderToStaticMarkup(
      createElement(BoardColumn, { status: 'done', label: 'Done', cards, cap: 20 }),
    );
    expect(markup.match(/board-card-/g)).toHaveLength(20);
    expect(markup).toContain('5 more not shown');
  });
});
