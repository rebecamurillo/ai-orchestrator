/**
 * `src/lib/diagram/svg.tsx` — the new run-status props `DiagramNode` and `DiagramGroup`
 * gain in Epic 8 (story 8.1).
 *
 * `diagram-svg.test.ts` owns the existing template-graph assertions; this file owns the
 * run-graph additions so the two stay independent and `diagram-svg.test.ts` stays frozen.
 *
 * 2026-09-24, run-diagram v3: the `RunDiagram` island this file imported to satisfy
 * `check-test-pairs.mjs` is deleted — it was an unreachable duplicate of `DiagramSection`
 * and survived only to be named here. Its pairing stub goes with it. Every assertion below
 * is about `lib/diagram/svg.tsx`, which the **template** diagram still renders, and stands
 * unchanged.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { DiagramGroup, DiagramNode } from '../../src/lib/diagram/svg';
import { layoutGraph } from '../../src/lib/diagram/layout';
import { STORY_GRAPH, EPIC_GRAPH } from './diagram-fixtures';

function placedStoryNode() {
  return layoutGraph(STORY_GRAPH).nodes.find((p) => p.node.id === 'build')!;
}

function placedEpicGroup() {
  return layoutGraph(EPIC_GRAPH).groups[0]!;
}

describe('DiagramNode run-status props (Epic 8)', () => {
  it('sets data-signal on the <g> from the token when token is present', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramNode, { placed: placedStoryNode(), token: 'BLK' }),
    );

    expect(markup).toContain('data-signal="needs-you"');
  });

  it('overrides the eyebrow to "now" when current is true', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramNode, { placed: placedStoryNode(), current: true }),
    );

    expect(markup).toContain('>now<');
  });

  it('renders the chip circle when token is present', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramNode, { placed: placedStoryNode(), token: 'BLK' }),
    );

    expect(markup).toContain('diagram-node-chip');
    expect(markup).toContain('<circle');
  });

  it('renders the token text right-aligned when token is present', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramNode, {
        placed: placedStoryNode(),
        token: 'BLK',
        current: true,
        substeps: ['sync done', 'build BLK'],
      }),
    );

    expect(markup).toContain('diagram-node-token');
    expect(markup).toContain('>BLK<');
  });

  it('renders the substeps text when substeps is non-empty', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramNode, {
        placed: placedStoryNode(),
        token: 'BLK',
        current: true,
        substeps: ['sync done', 'build BLK'],
      }),
    );

    expect(markup).toContain('diagram-node-substeps');
    expect(markup).toContain('sync done · build BLK');
  });

  it('sets data-signal on the <g> with the full trio of props', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramNode, {
        placed: placedStoryNode(),
        token: 'BLK',
        current: true,
        substeps: ['sync done', 'build BLK'],
      }),
    );

    expect(markup).toContain('data-signal="needs-you"');
    expect(markup).toContain('>now<');
    expect(markup).toContain('diagram-node-chip');
    expect(markup).toContain('sync done · build BLK');
  });

  it('leaves template-graph nodes visually unchanged when no run props are passed', () => {
    const markup = renderToStaticMarkup(createElement(DiagramNode, { placed: placedStoryNode() }));

    // No run-specific elements
    expect(markup).not.toContain('diagram-node-chip');
    expect(markup).not.toContain('diagram-node-token');
    expect(markup).not.toContain('diagram-node-substeps');
    expect(markup).not.toContain('data-signal');
    // Eyebrow is the kind word, not "now"
    expect(markup).not.toContain('>now<');
    expect(markup).toContain('>agent<');
  });

  it('omits chip and substeps when token and substeps are absent', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramNode, { placed: placedStoryNode(), current: true }),
    );

    expect(markup).not.toContain('diagram-node-chip');
    expect(markup).not.toContain('diagram-node-substeps');
  });

  it('spells no colour of its own even when token is present', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramNode, { placed: placedStoryNode(), token: 'BLK' }),
    );

    expect(markup).not.toContain('style=');
    expect(markup).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});

describe('DiagramGroup status prop (Epic 8)', () => {
  it('renders a group-token text element when status is not null', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramGroup, { placed: placedEpicGroup(), status: 'DON' }),
    );

    expect(markup).toContain('diagram-group-token');
    expect(markup).toContain('>DON<');
  });

  it('omits the group-token element when status is null (cancelled run)', () => {
    const markup = renderToStaticMarkup(
      createElement(DiagramGroup, { placed: placedEpicGroup(), status: null }),
    );

    expect(markup).not.toContain('diagram-group-token');
  });

  it('omits the group-token element when status prop is absent (template graph)', () => {
    const markup = renderToStaticMarkup(createElement(DiagramGroup, { placed: placedEpicGroup() }));

    expect(markup).not.toContain('diagram-group-token');
  });
});
