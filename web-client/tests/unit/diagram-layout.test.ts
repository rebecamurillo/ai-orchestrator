/**
 * `src/lib/diagram/layout.ts` — dagre placement plus the connectors this product draws (3.6).
 *
 * The layout is the one part of the diagram that has to be pure: `vitest.config.ts` runs
 * `environment: 'node'` with no DOM library, so nothing here can be measured in a browser.
 * dagre needs none — it is given every box's size and answers with positions — and the
 * connectors are computed from those positions rather than taken from dagre's splines,
 * because the brief asks for orthogonal hairlines and dagre answers with control points.
 */
import { describe, expect, it } from 'vitest';

import { GROUP_PADDING, NODE_HEIGHT, NODE_WIDTH, layoutGraph } from '../../src/lib/diagram/layout';
import { EMPTY, EPIC_GRAPH, STORY_GRAPH, node } from './diagram-fixtures';

describe('layoutGraph', () => {
  it('places one box per node, keyed by the node id and never by position', () => {
    const layout = layoutGraph(EPIC_GRAPH);

    expect(layout.nodes.map((placed) => placed.node.id)).toEqual([
      'checkout',
      'baseline',
      'stories.story',
      'stories.after',
      'push',
      'link',
    ]);
    for (const placed of layout.nodes) {
      expect(placed.width).toBe(NODE_WIDTH);
      expect(placed.height).toBe(NODE_HEIGHT);
    }
  });

  it('lays the ranks out left to right, so a later step is never left of an earlier one', () => {
    const layout = layoutGraph(STORY_GRAPH);
    const x = new Map(layout.nodes.map((placed) => [placed.node.id, placed.x]));

    expect(x.get('sync')!).toBeLessThan(x.get('build')!);
    expect(x.get('build')!).toBeLessThan(x.get('verify')!);
    expect(x.get('verify')!).toBeLessThan(x.get('commit-guard')!);
  });

  it('gives every placed box a finite position inside the reported extent', () => {
    const layout = layoutGraph(EPIC_GRAPH);

    expect(Number.isFinite(layout.width)).toBe(true);
    expect(Number.isFinite(layout.height)).toBe(true);
    for (const placed of [...layout.nodes, ...layout.groups]) {
      expect(Number.isFinite(placed.x)).toBe(true);
      expect(Number.isFinite(placed.y)).toBe(true);
      expect(placed.x).toBeGreaterThanOrEqual(0);
      expect(placed.y).toBeGreaterThanOrEqual(0);
      expect(placed.x + placed.width).toBeLessThanOrEqual(layout.width);
      expect(placed.y + placed.height).toBeLessThanOrEqual(layout.height);
    }
  });

  it('answers an empty extent for an empty graph, with no NaN in it', () => {
    const layout = layoutGraph(EMPTY);

    expect(layout).toEqual({ width: 0, height: 0, nodes: [], edges: [], groups: [] });
  });
});

describe('the connectors', () => {
  it('leaves the source box on its right edge and enters the target on its left', () => {
    const layout = layoutGraph(STORY_GRAPH);
    const placed = new Map(layout.nodes.map((entry) => [entry.node.id, entry]));
    const edge = layout.edges.find((entry) => entry.from === 'sync' && entry.to === 'build')!;

    const source = placed.get('sync')!;
    const target = placed.get('build')!;
    expect(edge.points[0]).toEqual({ x: source.x + source.width, y: source.y + source.height / 2 });
    expect(edge.points[edge.points.length - 1]).toEqual({
      x: target.x,
      y: target.y + target.height / 2,
    });
  });

  it('draws a straight two-point line when the two ranks share a row', () => {
    const layout = layoutGraph(STORY_GRAPH);
    const edge = layout.edges.find((entry) => entry.from === 'sync' && entry.to === 'build')!;

    // `story@1` is a single chain: dagre puts every node on one row
    expect(edge.points).toHaveLength(2);
    expect(edge.points[0]!.y).toBe(edge.points[1]!.y);
  });

  it('turns twice, at the midpoint between the two boxes, when the rows differ', () => {
    const branching = {
      nodes: [node('root'), node('left'), node('right')],
      edges: [
        { from: 'root', to: 'left' },
        { from: 'root', to: 'right' },
      ],
      groups: [],
    };

    const layout = layoutGraph(branching);
    const placed = new Map(layout.nodes.map((entry) => [entry.node.id, entry]));
    const edge = layout.edges.find((entry) => entry.to === 'left')!;

    expect(edge.points).toHaveLength(4);
    const [start, first, second, end] = edge.points;
    const midpoint = (start!.x + end!.x) / 2;
    expect(first).toEqual({ x: midpoint, y: start!.y });
    expect(second).toEqual({ x: midpoint, y: end!.y });
    expect(start!.y).toBe(placed.get('root')!.y + NODE_HEIGHT / 2);
    expect(end!.y).toBe(placed.get('left')!.y + NODE_HEIGHT / 2);
  });

  it('carries an id built from the two node ids, so React keys never use an index', () => {
    const layout = layoutGraph(EPIC_GRAPH);

    expect(layout.edges.map((edge) => edge.id)).toEqual([
      'checkout->baseline',
      'baseline->stories.story',
      'stories.story->stories.after',
      'stories.after->push',
      'push->link',
    ]);
  });

  it('drops an edge whose end no node carries, rather than drawing to nowhere', () => {
    const dangling = {
      nodes: [node('only')],
      edges: [
        { from: 'only', to: 'absent' },
        { from: 'absent', to: 'only' },
      ],
      groups: [],
    };

    expect(layoutGraph(dangling).edges).toEqual([]);
  });
});

describe('the group boxes', () => {
  it('encloses its members, padded, and is drawn from Group.members alone', () => {
    const layout = layoutGraph(EPIC_GRAPH);
    const placed = new Map(layout.nodes.map((entry) => [entry.node.id, entry]));
    const group = layout.groups.find((entry) => entry.group.id === 'stories')!;

    const members = ['stories.story', 'stories.after'].map((id) => placed.get(id)!);
    const left = Math.min(...members.map((member) => member.x));
    const top = Math.min(...members.map((member) => member.y));
    const right = Math.max(...members.map((member) => member.x + member.width));
    const bottom = Math.max(...members.map((member) => member.y + member.height));

    expect(group.x).toBe(left - GROUP_PADDING);
    expect(group.y).toBe(top - GROUP_PADDING);
    expect(group.width).toBe(right - left + GROUP_PADDING * 2);
    expect(group.height).toBe(bottom - top + GROUP_PADDING * 2);
  });

  it('encloses only the members that exist, and ignores an id no node carries', () => {
    const withGhost = {
      ...EPIC_GRAPH,
      groups: [
        {
          id: 'stories',
          label: 'stories',
          kind: 'for_each' as const,
          members: ['stories.story', 'nothing-has-this-id', 'stories.after'],
        },
      ],
    };

    const drawn = layoutGraph(withGhost).groups[0]!;
    const complete = layoutGraph(EPIC_GRAPH).groups[0]!;

    expect([drawn.x, drawn.y, drawn.width, drawn.height]).toEqual([
      complete.x,
      complete.y,
      complete.width,
      complete.height,
    ]);
  });

  it('draws no box at all for a group none of whose members exist', () => {
    const orphaned = {
      ...STORY_GRAPH,
      groups: [
        { id: 'ghost', label: 'ghost', kind: 'for_each' as const, members: ['nobody', 'nothing'] },
      ],
    };

    expect(layoutGraph(orphaned).groups).toEqual([]);
  });
});
