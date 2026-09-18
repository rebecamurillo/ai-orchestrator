/**
 * `src/lib/diagram/svg.tsx::DiagramGroup` — k/n step-count chip (story 1-5).
 *
 * Minimal AD-18 pair: proves DiagramGroup accepts k/n props and renders the k/n count text
 * when n > 0, and omits it when n === 0.
 *
 * TDD (AD-18): written first — must fail before svg.tsx DiagramGroup changes.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { DiagramGroup } from '../../src/lib/diagram/svg';
import { layoutGraph } from '../../src/lib/diagram/layout';
import { EPIC_GRAPH } from './diagram-fixtures';

function placedEpicGroup() {
  return layoutGraph(EPIC_GRAPH).groups[0]!;
}

describe('DiagramGroup', () => {
  it('is a function component', () => {
    expect(typeof DiagramGroup).toBe('function');
  });

  it('renders k/n count text when n > 0', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramGroup, { placed: placedEpicGroup(), status: 'done', k: 3, n: 5 }),
    );

    expect(markup).toContain('diagram-group-kn');
    expect(markup).toContain('3/5 steps');
  });

  it('omits the k/n count text when n is 0', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramGroup, { placed: placedEpicGroup(), status: 'skipped', k: 0, n: 0 }),
    );

    expect(markup).not.toContain('diagram-group-kn');
  });

  it('omits the k/n count text when n is absent', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramGroup, { placed: placedEpicGroup(), status: 'done' }),
    );

    expect(markup).not.toContain('diagram-group-kn');
  });

  it('adds data-status attribute to the outer group element', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramGroup, { placed: placedEpicGroup(), status: 'running' }),
    );

    expect(markup).toContain('data-status="running"');
  });

  it('renders the chip circle when status is present', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramGroup, { placed: placedEpicGroup(), status: 'done' }),
    );

    expect(markup).toContain('diagram-group-chip');
    expect(markup).toContain('<circle');
  });
});
