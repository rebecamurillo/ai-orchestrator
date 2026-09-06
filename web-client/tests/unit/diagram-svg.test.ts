/**
 * `src/lib/diagram/svg.tsx` — the three renderers and `gateWord`, as static markup (3.6).
 *
 * Unit tests are `.test.ts` only (`vitest.config.ts`'s `include`), so no JSX appears here:
 * React is driven through `createElement` and `renderToStaticMarkup`, which needs no DOM and
 * is what lets a renderer be asserted at all in `environment: 'node'`.
 *
 * `status` and `current` are accepted and unused today. They are asserted here because Epic 8
 * colours the same island with a Run's statuses, and a prop that arrives then would mean
 * restructuring the renderer rather than adding a token to it.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import {
  DiagramEdge,
  DiagramGroup,
  DiagramNode,
  gateWord,
  kindWord,
} from '../../src/lib/diagram/svg';
import { layoutGraph } from '../../src/lib/diagram/layout';
import { EPIC_GRAPH, STORY_GRAPH, node } from './diagram-fixtures';

/** The colour values `tokens.css` reserves for signal. None may appear in this diagram. */
const SIGNAL = ['--color-signal-run', '--color-signal-needs-you', '--color-signal-failed'];

function placedNode(graph: typeof EPIC_GRAPH, id: string) {
  return layoutGraph(graph).nodes.find((entry) => entry.node.id === id)!;
}

function renderNode(graph: typeof EPIC_GRAPH, id: string, extra: Record<string, unknown> = {}) {
  return renderToStaticMarkup(
    createElement(DiagramNode, { placed: placedNode(graph, id), ...extra }),
  );
}

describe('gateWord', () => {
  it('reads back the word the Template declared', () => {
    expect(gateWord(node('a', { gate: 'deterministic' }))).toBe('deterministic');
    expect(gateWord(node('a', { gate: 'liveness' }))).toBe('liveness');
    expect(gateWord(node('a', { gate: 'human' }))).toBe('human');
  });

  it('reads the plain word for a step the Template gated with nothing (NFR-2)', () => {
    expect(gateWord(node('a', { gate: 'unvalidated' }))).toBe('unvalidated');
  });

  it('has no word for a collapsed call, which is a path segment and never a stop', () => {
    expect(gateWord(node('a', { kind: 'template', gate: null }))).toBeNull();
  });
});

describe('kindWord', () => {
  /** Every kind `application/steps`' registry holds — the one enumeration there is (AD-9). */
  const KINDS = [
    'plan.check',
    'git.worktree',
    'git.sync',
    'shell',
    'agent',
    'git.commit',
    'git.push',
    'pr.link',
    'checkpoint',
    'template',
    'bmad.install',
  ];

  it('reads a dotted kind as its last segment', () => {
    expect(kindWord('git.worktree')).toBe('worktree');
    expect(kindWord('pr.link')).toBe('link');
    expect(kindWord('bmad.install')).toBe('install');
  });

  it('leaves a kind that has no dot exactly as it is', () => {
    expect(kindWord('agent')).toBe('agent');
    expect(kindWord('template')).toBe('template');
    expect(kindWord('checkpoint')).toBe('checkpoint');
    expect(kindWord('shell')).toBe('shell');
  });

  it('conflates no two kinds: the whole registry maps to distinct words', () => {
    const words = KINDS.map(kindWord);

    expect(new Set(words).size).toBe(KINDS.length);
  });
});

describe('DiagramNode', () => {
  it('carries the node id as its test id, byte for byte, dots and all', () => {
    const markup = renderNode(EPIC_GRAPH, 'stories.story');

    expect(markup).toContain('data-testid="diagram-node-stories.story"');
  });

  it('reads a collapsed call as {name}@{version} under the eyebrow template', () => {
    const markup = renderNode(EPIC_GRAPH, 'stories.story');

    expect(markup).toContain('>story@1<');
    expect(markup).toContain('>template<');
    expect(markup).not.toContain('>unvalidated<');
  });

  it('reads a dotted kind as its last segment, so a fixed-width box can hold it', () => {
    expect(renderNode(EPIC_GRAPH, 'checkout')).toContain('>worktree<');
  });

  it('omits the gate line entirely on a call, rather than filling it with a word', () => {
    const markup = renderNode(EPIC_GRAPH, 'stories.story');

    expect(markup).not.toContain('diagram-node-gate');
  });

  it('reads an item checkpoint as the plain word human', () => {
    const markup = renderNode(EPIC_GRAPH, 'stories.after');

    expect(markup).toContain('>human<');
    expect(markup).toContain('data-human="true"');
  });

  it('draws a hairline under the word human, and under no other gate', () => {
    expect(renderNode(EPIC_GRAPH, 'stories.after')).toContain('diagram-node-hairline');
    expect(renderNode(EPIC_GRAPH, 'checkout')).not.toContain('diagram-node-hairline');
    expect(renderNode(STORY_GRAPH, 'build')).not.toContain('diagram-node-hairline');
  });

  it('starts the hairline at the word and keeps it inside the box it underlines', () => {
    const placed = placedNode(EPIC_GRAPH, 'stories.after');
    const markup = renderNode(EPIC_GRAPH, 'stories.after');
    const line = /<line[^>]*class="diagram-node-hairline"[^>]*>/.exec(markup)![0];
    const value = (attribute: string) =>
      Number(new RegExp(`${attribute}="([^"]+)"`).exec(line)![1]);

    expect(value('y1')).toBe(value('y2'));
    expect(value('y1')).toBeGreaterThan(placed.y);
    expect(value('y1')).toBeLessThan(placed.y + placed.height);
    expect(value('x1')).toBeGreaterThan(placed.x);
    expect(value('x2')).toBeLessThan(placed.x + placed.width);
  });

  it('marks the step that dispatches a harness, so the stylesheet can accent its border', () => {
    const markup = renderNode(STORY_GRAPH, 'build');

    expect(markup).toContain('data-agent="true"');
    expect(markup).toContain('>agent<');
    expect(markup).toContain('>liveness<');
  });

  it('reads a step the Template gated with nothing as the plain word unvalidated', () => {
    const ungated = {
      nodes: [node('draft', { gate: 'unvalidated' })],
      edges: [],
      groups: [],
    };

    expect(renderNode(ungated, 'draft')).toContain('>unvalidated<');
  });

  it('draws a square box: no rx, no ry, no rounded corner anywhere', () => {
    const markup = renderNode(STORY_GRAPH, 'build');

    expect(markup).not.toMatch(/\srx=/);
    expect(markup).not.toMatch(/\sry=/);
  });

  it('spells no colour of its own: every fill and stroke comes from the stylesheet', () => {
    const markup = renderNode(STORY_GRAPH, 'build');

    expect(markup).not.toContain('style=');
    expect(markup).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    for (const token of SIGNAL) expect(markup).not.toContain(token);
  });

  it('accepts the status and current props Epic 8 fills in, and draws them as data', () => {
    const markup = renderNode(STORY_GRAPH, 'build', { status: 'RUN', current: true });

    expect(markup).toContain('data-status="RUN"');
    expect(markup).toContain('data-current="true"');
  });

  it('carries neither attribute while those props are absent, as they are today', () => {
    const markup = renderNode(STORY_GRAPH, 'build');

    expect(markup).not.toContain('data-status');
    expect(markup).not.toContain('data-current');
  });
});

describe('DiagramGroup', () => {
  it('carries the group id as its test id and names the loop', () => {
    const placed = layoutGraph(EPIC_GRAPH).groups[0]!;

    const markup = renderToStaticMarkup(createElement(DiagramGroup, { placed }));

    expect(markup).toContain('data-testid="diagram-group-stories"');
    expect(markup).toContain('>stories<');
  });

  it('draws a dashed, unfilled rectangle and no colour of its own', () => {
    const placed = layoutGraph(EPIC_GRAPH).groups[0]!;

    const markup = renderToStaticMarkup(createElement(DiagramGroup, { placed }));

    expect(markup).toContain('diagram-group-box');
    expect(markup).not.toContain('style=');
    expect(markup).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});

describe('DiagramEdge', () => {
  it('draws the computed polyline, point for point', () => {
    const placed = layoutGraph(STORY_GRAPH).edges[0]!;

    const markup = renderToStaticMarkup(createElement(DiagramEdge, { placed }));

    const expected = placed.points.map((point) => `${point.x},${point.y}`).join(' ');
    expect(markup).toContain(`points="${expected}"`);
  });

  it('spells no colour of its own', () => {
    const placed = layoutGraph(STORY_GRAPH).edges[0]!;

    const markup = renderToStaticMarkup(createElement(DiagramEdge, { placed }));

    expect(markup).not.toContain('style=');
    expect(markup).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
