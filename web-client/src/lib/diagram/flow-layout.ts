/**
 * Where every v3 card, connector and retry chip goes — the hierarchy placed, as the
 * `{nodes, edges}` React Flow renders.
 *
 * React Flow is **never imported here**: the element that consumes this lives in
 * `components/run/diagram/FlowCanvas.tsx`, and keeping the maths out of it is what lets the
 * whole layout be asserted under `environment: 'node'` (the same split `diagram/layout.ts`
 * documents for the template diagram, and what holds `src/lib/**` at its 90 % line gate
 * without a DOM). The shapes below are structurally what React Flow's `Node`/`Edge` want, so
 * `FlowCanvas` consumes them without a cast.
 *
 * **dagre answers the columns.** `rankdir: 'LR'` with one width per rank, so the ranks the
 * hierarchy collapsed to read as columns at the x dagre ranks them to, and no size is ever
 * measured from the DOM.
 *
 * **The plan answers the rows.** dagre's own vertical order is whatever minimises edge
 * crossings, and on a crossing-free tree that is free to come out reversed — which it does.
 * EXPERIENCE-v1 §2.2 fixes the order instead: *siblings stack vertically in spec order*
 * (`epics.yaml`, then `stories.yaml`), because the operator reads the run down the column
 * the way the plan lists it. So `stackVertically` below walks the tree in the plan's own
 * order, stacking what has no children and centring every parent on the span of the children
 * it holds — the artboard's shape, and the one thing a crossing heuristic cannot be asked for.
 *
 * **The attempts gutter is placed by hand.** dagre would give a retry chip a rank of its
 * own, which would push a rank-2 agent's chip into the AGENTS column. The artboard puts
 * every chip in one gutter right of the widest card instead, with a dashed edge looping
 * back — so that is a column computed after dagre has answered, not a rank inside it, and it
 * carries a cursor of its own so two agents retrying at the same height cannot overlap.
 */
import dagre from '@dagrejs/dagre';

import type { Hierarchy, HierarchyNode, RetryChip } from './run-tree';

/** Card sizes, from the artboard (`mockups/RunDiagram-v3.html`). */
export const ROOT_SIZE = { width: 180, height: 76 };
/** A frame-less Run's root owns a guardrail strip, and a strip needs a card to sit in. */
export const ROOT_GUARDRAIL_SIZE = { width: 330, height: 102 };
export const EPIC_SIZE = { width: 330, height: 102 };
export const STORY_SIZE = { width: 228, height: 82 };
export const EPIC_AGENT_SIZE = { width: 228, height: 102 };
export const STORY_AGENT_SIZE = { width: 216, height: 102 };
export const CHIP_SIZE = { width: 104, height: 40 };
/** The column head above a rank — a node of the canvas, so it pans and zooms with it. */
export const HEAD_HEIGHT = 18;
/** Between a head and the first card under it. */
export const HEAD_GAP = 14;

export const RANK_SEPARATION = 56;
export const NODE_SEPARATION = 16;
export const MARGIN = 24;
/** Clear space between the widest card and the attempts gutter. */
export const GUTTER_GAP = 96;
/** Between two chips of one agent, and between two agents' stacks. */
export const CHIP_GAP = 12;

export type FlowNodeType =
  'runHead' | 'runRoot' | 'runEpic' | 'runStory' | 'runAgent' | 'runRetry' | 'runMore';

/**
 * What a node hands its renderer, as a discriminated union: a card carries a `HierarchyNode`,
 * a chip carries a `RetryChip`, and the gutter's overflow chip carries a count. Narrowing on
 * `kind` is what replaced the `data.node!` assertions — a renderer can no longer read a field
 * the node it was handed does not have.
 */
export type FlowNodeData =
  | { kind: 'card'; node: HierarchyNode }
  | { kind: 'chip'; chip: RetryChip; ownerPath: string }
  | { kind: 'more'; overflow: number; ownerPath: string }
  | { kind: 'head'; label: string; rank: number };

export interface FlowNode {
  id: string;
  type: FlowNodeType;
  position: { x: number; y: number };
  width: number;
  height: number;
  data: FlowNodeData;
  draggable: boolean;
  selectable: boolean;
  connectable: boolean;
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  /**
   * Handles are named because an agent card carries two targets: `in` on its left, where its
   * story joins it, and `retry` on its right, where a chip in the gutter loops back into it.
   */
  sourceHandle: 'out' | 'back';
  targetHandle: 'in' | 'retry';
  /** `smoothstep` for the orthogonal hairlines, `default` for a retry's curve. */
  type: 'smoothstep' | 'default';
  className: string;
  label?: string;
  markerEnd: { type: 'arrowclosed'; width: number; height: number; color: string };
}

export interface FlowLayout {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

const HAIRLINE_MARKER = {
  type: 'arrowclosed',
  width: 12,
  height: 12,
  color: 'var(--color-line-strong)',
} as const;

const RETRY_MARKER = {
  type: 'arrowclosed',
  width: 12,
  height: 12,
  color: 'var(--color-signal-failed)',
} as const;

/** The box dagre is handed for one card — one width per rank, so the ranks line up. */
export function sizeOf(node: HierarchyNode): { width: number; height: number } {
  if (node.kind === 'root') return node.guardrail === null ? ROOT_SIZE : ROOT_GUARDRAIL_SIZE;
  if (node.kind === 'epic') return EPIC_SIZE;
  if (node.kind === 'story') return STORY_SIZE;
  // read off what holds the card, not off the rank: ranks collapse, and a frame-less Run's
  // agent sits in column 1 while still being an agent under the root
  return node.parentKind === 'story' ? STORY_AGENT_SIZE : EPIC_AGENT_SIZE;
}

const TYPE_OF: Record<HierarchyNode['kind'], FlowNodeType> = {
  root: 'runRoot',
  epic: 'runEpic',
  story: 'runStory',
  agent: 'runAgent',
};

/** The id a chip is drawn under — path-bearing, so `wf-diagram-retry-<path>-<n>` reads off it. */
export function chipId(node: Pick<HierarchyNode, 'id'>, chip: Pick<RetryChip, 'n'>): string {
  return `retry:${node.id}:${chip.n}`;
}

/** The id of the chip standing for the failures the gutter did not draw. */
export function moreChipId(node: Pick<HierarchyNode, 'id'>): string {
  return `retry:${node.id}:more`;
}

/**
 * Every node's top edge, in the plan's own order: a card with no children takes the next
 * slot down the column, and a card that holds children is centred on their span.
 *
 * A parent taller than the subtree under it would otherwise reach above where that subtree
 * started and collide with the sibling above; when that happens the subtree is pushed down
 * instead, which is the one case where a child moves for its parent rather than the reverse.
 */
export function stackVertically(hierarchy: Hierarchy): Map<string, number> {
  // `hierarchy.nodes` arrives rank-then-spec ordered, so every child list below is spec order
  const children = new Map<string, HierarchyNode[]>();
  const drawn = new Set(hierarchy.nodes.map((node) => node.id));
  for (const node of hierarchy.nodes) {
    if (node.parentId === null || !drawn.has(node.parentId)) continue;
    const siblings = children.get(node.parentId);
    if (siblings === undefined) children.set(node.parentId, [node]);
    else siblings.push(node);
  }

  const top = new Map<string, number>();
  let cursor = MARGIN;

  /** Places `node` and everything under it; answers the ids it placed. */
  function place(node: HierarchyNode): string[] {
    const height = sizeOf(node).height;
    const below = children.get(node.id) ?? [];
    if (below.length === 0) {
      top.set(node.id, cursor);
      cursor += height + NODE_SEPARATION;
      return [node.id];
    }

    const start = cursor;
    const placed: string[] = [];
    for (const child of below) placed.push(...place(child));

    const first = below[0]!;
    const last = below[below.length - 1]!;
    const span = top.get(first.id)! + top.get(last.id)! + sizeOf(last).height;
    let y = span / 2 - height / 2;
    if (y < start) {
      const shift = start - y;
      for (const id of placed) top.set(id, top.get(id)! + shift);
      cursor += shift;
      y = start;
    }
    top.set(node.id, y);
    cursor = Math.max(cursor, y + height + NODE_SEPARATION);
    return [node.id, ...placed];
  }

  for (const node of hierarchy.nodes) {
    if (node.parentId === null || !drawn.has(node.parentId)) place(node);
  }
  return top;
}

/** `{nodes, edges}` placed. An empty hierarchy is an empty layout, never a NaN one. */
export function flowLayout(hierarchy: Hierarchy): FlowLayout {
  // a fresh pair every call: these arrays reach `useNodesState`, which owns what it is given
  if (hierarchy.nodes.length === 0) return { nodes: [], edges: [] };

  const laid = new dagre.graphlib.Graph();
  laid.setGraph({
    rankdir: 'LR',
    ranksep: RANK_SEPARATION,
    nodesep: NODE_SEPARATION,
    marginx: MARGIN,
    marginy: MARGIN,
  });
  laid.setDefaultEdgeLabel(() => ({}));

  // a fresh object per node: `dagre.layout` writes `x`/`y` into the value it was handed, and
  // `sizeOf` answers with one shared constant per rank — handing it in directly would make
  // every card of a rank share one box, and the whole rank would stack on one point.
  for (const node of hierarchy.nodes) laid.setNode(node.id, { ...sizeOf(node) });
  for (const edge of hierarchy.edges) {
    if (laid.hasNode(edge.from) && laid.hasNode(edge.to)) laid.setEdge(edge.from, edge.to);
  }
  dagre.layout(laid);

  const top = stackVertically(hierarchy);
  // every card drops by the head band, so the heads have a row of their own above the tree
  const band = HEAD_HEIGHT + HEAD_GAP;

  const cards: FlowNode[] = hierarchy.nodes.map((node) => {
    const size = sizeOf(node);
    const box = laid.node(node.id);
    return {
      id: node.id,
      type: TYPE_OF[node.kind],
      position: { x: box.x - size.width / 2, y: top.get(node.id)! + band },
      width: size.width,
      height: size.height,
      data: { kind: 'card', node },
      draggable: true,
      selectable: false,
      connectable: false,
    };
  });

  // The column heads are nodes of the canvas, not a strip above it. A static row outside the
  // pannable, `fitView`-scaled transform sits over the wrong columns the moment the operator
  // pans or zooms, and the spine's promise is that the heads describe the columns actually
  // drawn. Inside the transform they move with what they name. They are not draggable —
  // dragging a label off its column would break the same promise by hand.
  const heads: FlowNode[] = hierarchy.heads.map((label, rank) => {
    const column = cards.filter((card) => hierarchy.ranks[rank]!.some((n) => n.id === card.id));
    const x = Math.min(...column.map((card) => card.position.x));
    const width = Math.max(...column.map((card) => card.width));
    return {
      id: `head:${rank}`,
      type: 'runHead',
      position: { x, y: MARGIN },
      width,
      height: HEAD_HEIGHT,
      data: { kind: 'head', label, rank },
      draggable: false,
      selectable: false,
      connectable: false,
    };
  });

  const gutterX = Math.max(...cards.map((card) => card.position.x + card.width)) + GUTTER_GAP;

  const chips: FlowNode[] = [];
  const retryEdges: FlowEdge[] = [];
  // one cursor down the gutter: two agents retrying at similar heights would otherwise stack
  // their chips over each other, because each stack only knows its own card
  let gutterCursor = -Infinity;
  const retrying = hierarchy.nodes
    .filter((node) => node.retries.length > 0)
    .sort((a, b) => top.get(a.id)! - top.get(b.id)!);

  for (const node of retrying) {
    const card = cards.find((entry) => entry.id === node.id)!;
    const drawn = node.retries.length + (node.retryOverflow > 0 ? 1 : 0);
    const stack = drawn * CHIP_SIZE.height + (drawn - 1) * CHIP_GAP;
    let y = Math.max(card.position.y + card.height / 2 - stack / 2, gutterCursor);
    gutterCursor = y + stack + CHIP_GAP;

    const loopBack = (id: string): FlowEdge => ({
      id: `${id}->${node.id}`,
      source: id,
      target: node.id,
      sourceHandle: 'back',
      targetHandle: 'retry',
      type: 'default',
      className: 'wf-flow-edge-retry',
      label: 'retry',
      markerEnd: RETRY_MARKER,
    });

    // the overflow chip stands for the attempts *before* the ones drawn, so it goes above
    // them — the gutter reads oldest at the top, the way the run happened
    if (node.retryOverflow > 0) {
      const id = moreChipId(node);
      chips.push({
        id,
        type: 'runMore',
        position: { x: gutterX, y },
        width: CHIP_SIZE.width,
        height: CHIP_SIZE.height,
        data: { kind: 'more', overflow: node.retryOverflow, ownerPath: node.path },
        draggable: true,
        selectable: false,
        connectable: false,
      });
      retryEdges.push(loopBack(id));
      y += CHIP_SIZE.height + CHIP_GAP;
    }

    for (const chip of node.retries) {
      const id = chipId(node, chip);
      chips.push({
        id,
        type: 'runRetry',
        position: { x: gutterX, y },
        width: CHIP_SIZE.width,
        height: CHIP_SIZE.height,
        data: { kind: 'chip', chip, ownerPath: node.path },
        draggable: true,
        selectable: false,
        connectable: false,
      });
      retryEdges.push(loopBack(id));
      y += CHIP_SIZE.height + CHIP_GAP;
    }
  }

  const edges: FlowEdge[] = hierarchy.edges.map((edge) => ({
    id: edge.id,
    source: edge.from,
    target: edge.to,
    sourceHandle: 'out',
    targetHandle: 'in',
    type: 'smoothstep',
    className: 'wf-flow-edge',
    markerEnd: HAIRLINE_MARKER,
  }));

  return { nodes: [...heads, ...cards, ...chips], edges: [...edges, ...retryEdges] };
}
