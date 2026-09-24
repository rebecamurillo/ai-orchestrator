/**
 * `src/components/run/diagram/FlowCanvas.tsx` — the React Flow element of the v3 diagram.
 *
 * The element itself measures a DOM and is exercised by `tests/e2e/run-diagram.spec.ts`.
 * What is asserted here is what a DOM would not show and a regression would not announce:
 * that every node type the layout emits has a renderer, that `withHandlers` folds the Run id
 * and the toggle into each card without moving it, and that `mergePositions` — the rule that
 * decides whether a drag survives — keeps a position across a poll and drops it on a reset.
 */
import { describe, expect, it } from 'vitest';

import FlowCanvas, {
  mergePositions,
  nodeTypes,
  withHandlers,
  type CardNode,
} from '../../src/components/run/diagram/FlowCanvas';
import {
  AgentNode,
  EpicNode,
  HeadNode,
  MoreNode,
  RetryNode,
  RootNode,
  StoryNode,
} from '../../src/components/run/diagram/nodes';
import { flowLayout } from '../../src/lib/diagram/flow-layout';
import { buildHierarchy } from '../../src/lib/diagram/run-tree';
import { frameLessGraph, frameLessSteps, twoEpicGraph, twoEpicSteps } from '../fixtures/run-graph';

const OPEN = new Set(['epics[1]', 'epics[1].stories[0]']);

const LAYOUT = flowLayout(buildHierarchy(twoEpicGraph(), twoEpicSteps(), OPEN));

const RETRIED = flowLayout(
  buildHierarchy(
    twoEpicGraph(),
    twoEpicSteps().map((row) =>
      row.path === 'epics[1].stories[0].build' ? { ...row, attempts: 9, status: 'error' } : row,
    ),
    OPEN,
  ),
);

const noop = () => undefined;

describe('FlowCanvas', () => {
  it('is the component DiagramSection mounts', () => {
    expect(typeof FlowCanvas).toBe('function');
  });
});

describe('nodeTypes', () => {
  it('maps every type to the component that draws it', () => {
    // the key set alone would pass with every key pointing at the same renderer
    expect(nodeTypes).toEqual({
      runHead: HeadNode,
      runRoot: RootNode,
      runEpic: EpicNode,
      runStory: StoryNode,
      runAgent: AgentNode,
      runRetry: RetryNode,
      runMore: MoreNode,
    });
  });

  it('covers every type the layout emits, gutter and overflow chip included', () => {
    const emitted = new Set(
      [
        ...LAYOUT.nodes,
        ...RETRIED.nodes,
        ...flowLayout(buildHierarchy(frameLessGraph(), frameLessSteps(), new Set())).nodes,
      ].map((node) => node.type),
    );

    // heads, all four card kinds, a retry chip and the `+k` chip: every key is exercised
    expect([...emitted].sort()).toEqual(Object.keys(nodeTypes).sort());
    for (const type of emitted) expect(Object.keys(nodeTypes)).toContain(type);
  });
});

describe('withHandlers', () => {
  it('folds the Run id and the toggle into each card, and moves nothing', () => {
    const withData = withHandlers(LAYOUT, 'r1', noop);

    expect(withData).toHaveLength(LAYOUT.nodes.length);
    for (const [index, node] of withData.entries()) {
      const source = LAYOUT.nodes[index]!;
      expect(node.id).toBe(source.id);
      expect(node.position).toEqual(source.position);
      expect(node.data.runId).toBe('r1');
      expect(node.data.onToggle).toBe(noop);
      expect(node.data.kind).toBe(source.data.kind);
    }
  });
});

describe('mergePositions', () => {
  function at(id: string, x: number, y: number): CardNode {
    return { id, type: 'runAgent', position: { x, y }, data: {} as CardNode['data'] };
  }

  it('keeps where the operator put a card, and takes everything else from the layout', () => {
    const merged = mergePositions([at('a', 900, 900)], [at('a', 10, 20), at('b', 30, 40)], false);

    expect(merged.map((node) => [node.id, node.position])).toEqual([
      ['a', { x: 900, y: 900 }],
      ['b', { x: 30, y: 40 }],
    ]);
  });

  it('takes the computed data even for a card it did not move', () => {
    const previous = [
      { ...at('a', 900, 900), data: { kind: 'stale' } as unknown as CardNode['data'] },
    ];
    const computed = [
      { ...at('a', 10, 20), data: { kind: 'fresh' } as unknown as CardNode['data'] },
    ];

    expect(mergePositions(previous, computed, false)[0]!.data).toEqual({ kind: 'fresh' });
  });

  it('drops every dragged position on a reset', () => {
    // *reset layout*, or an expand that changed the shape of the tree: keeping the old
    // positions dropped the newly revealed children on the cards already placed
    const merged = mergePositions([at('a', 900, 900)], [at('a', 10, 20)], true);

    expect(merged[0]!.position).toEqual({ x: 10, y: 20 });
  });

  it('places a card the previous list never held, so a growing plan lands somewhere', () => {
    const merged = mergePositions([], [at('a', 10, 20)], false);

    expect(merged[0]!.position).toEqual({ x: 10, y: 20 });
  });
});
