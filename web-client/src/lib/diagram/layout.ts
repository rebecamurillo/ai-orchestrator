/**
 * Where every box, connector and loop rectangle of a Template diagram goes (3.6).
 *
 * Pure over the `GraphOut` the API answers: nothing here reads YAML (AD-15), and nothing
 * here measures a DOM. dagre needs neither — it is handed every box's size and answers with
 * positions — which is what lets the whole layout be asserted in `environment: 'node'`, where
 * `vitest.config.ts` runs and no DOM library exists.
 *
 * **Left to right.** `rankdir: 'LR'` is the direction the brief fixes: a Template reads as a
 * sequence, and a reader follows it the way they read the file.
 *
 * **The connectors are computed, not taken from dagre.** dagre answers each edge with spline
 * control points; the brief asks for orthogonal hairlines. So an edge here leaves the source
 * box's right edge, enters the target's left edge, and turns twice at the midpoint between
 * them — `(x1,y1) -> (mx,y1) -> (mx,y2) -> (x2,y2)` — collapsing to a straight two-point line
 * when the two boxes share a row, which is every edge of a Template with no branch. Two
 * points rather than four for that case is not an optimisation: a polyline with a redundant
 * vertex renders a visible seam at a hairline width.
 *
 * **Ids are the join key.** An edge carries `{from, to}` and an id built from the two, a
 * placed node carries its `Node`, and a group is resolved through `Group.members`. Nothing is
 * keyed on array position, so the last-valid rule (`diagram-state.ts`) can compare two graphs
 * node id by node id.
 *
 * **A group box is drawn from `members` alone.** It is the bounding box of the members that
 * exist, padded. An id no node carries is ignored rather than reaching dagre, and a group
 * none of whose members exist draws nothing at all: the API is the one authority on the
 * graph, and a diagram that crashed on a shape it did not expect would take the screen with
 * it.
 */
import dagre from '@dagrejs/dagre';

import type { components } from '../../api/schema';

type Graph = components['schemas']['GraphOut'];
type NodeOut = components['schemas']['NodeOut'];
type GroupOut = components['schemas']['GroupOut'];

/** Every box is the same size: the diagram is a sequence, not a treemap. */
export const NODE_WIDTH = 132;
export const NODE_HEIGHT = 46;

/** Between two ranks, and between two boxes of one rank. */
export const RANK_SEPARATION = 40;
export const NODE_SEPARATION = 16;

/** How far a loop's rectangle stands off the members it encloses. */
export const GROUP_PADDING = 10;

/** The clear space around everything, wide enough for a group label above its box. */
export const MARGIN = 18;

export interface Point {
  x: number;
  y: number;
}

export interface PlacedNode {
  node: NodeOut;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PlacedEdge {
  /** `{from}->{to}`: a React key that is never an array index. */
  id: string;
  from: string;
  to: string;
  points: Point[];
}

export interface PlacedGroup {
  group: GroupOut;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface DiagramLayout {
  width: number;
  height: number;
  nodes: PlacedNode[];
  edges: PlacedEdge[];
  groups: PlacedGroup[];
}

const EMPTY_LAYOUT: DiagramLayout = { width: 0, height: 0, nodes: [], edges: [], groups: [] };

/** `{nodes, edges, groups}` placed. An empty graph is an empty extent, never a NaN one. */
export function layoutGraph(graph: Graph): DiagramLayout {
  if (graph.nodes.length === 0) return EMPTY_LAYOUT;

  const placed = placeNodes(graph);
  const byId = new Map(placed.map((entry) => [entry.node.id, entry]));
  const edges = graph.edges.flatMap((edge) => connector(edge.from, edge.to, byId));
  const groups = graph.groups.flatMap((group) => enclose(group, byId));

  return { ...extent([...placed, ...groups]), nodes: placed, edges, groups };
}

/** dagre's placement, converted from box centres to the top-left corners SVG draws from. */
function placeNodes(graph: Graph): PlacedNode[] {
  const laid = new dagre.graphlib.Graph();
  laid.setGraph({
    rankdir: 'LR',
    ranksep: RANK_SEPARATION,
    nodesep: NODE_SEPARATION,
    // the group rectangle stands outside its members, so the margin has to clear it too
    marginx: MARGIN + GROUP_PADDING,
    marginy: MARGIN + GROUP_PADDING,
  });
  laid.setDefaultEdgeLabel(() => ({}));

  for (const node of graph.nodes) {
    laid.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of graph.edges) {
    if (laid.hasNode(edge.from) && laid.hasNode(edge.to)) laid.setEdge(edge.from, edge.to);
  }
  dagre.layout(laid);

  return graph.nodes.map((node) => {
    const box = laid.node(node.id);
    return {
      node,
      x: box.x - NODE_WIDTH / 2,
      y: box.y - NODE_HEIGHT / 2,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
    };
  });
}

/** One orthogonal hairline, or nothing at all when either end names no node. */
function connector(from: string, to: string, byId: Map<string, PlacedNode>): PlacedEdge[] {
  const source = byId.get(from);
  const target = byId.get(to);
  if (source === undefined || target === undefined) return [];

  const start = { x: source.x + source.width, y: source.y + source.height / 2 };
  const end = { x: target.x, y: target.y + target.height / 2 };
  const midpoint = (start.x + end.x) / 2;
  const points =
    start.y === end.y
      ? [start, end]
      : [start, { x: midpoint, y: start.y }, { x: midpoint, y: end.y }, end];

  return [{ id: `${from}->${to}`, from, to, points }];
}

/** The padded bounding box of the members that exist; nothing when none of them do. */
function enclose(group: GroupOut, byId: Map<string, PlacedNode>): PlacedGroup[] {
  const members = group.members
    .map((id) => byId.get(id))
    .filter((member): member is PlacedNode => member !== undefined);
  if (members.length === 0) return [];

  const left = Math.min(...members.map((member) => member.x));
  const top = Math.min(...members.map((member) => member.y));
  const right = Math.max(...members.map((member) => member.x + member.width));
  const bottom = Math.max(...members.map((member) => member.y + member.height));

  return [
    {
      group,
      x: left - GROUP_PADDING,
      y: top - GROUP_PADDING,
      width: right - left + GROUP_PADDING * 2,
      height: bottom - top + GROUP_PADDING * 2,
    },
  ];
}

/** The drawing surface: everything placed, plus the margin, rounded to whole pixels. */
function extent(boxes: { x: number; y: number; width: number; height: number }[]): {
  width: number;
  height: number;
} {
  return {
    width: Math.ceil(Math.max(...boxes.map((box) => box.x + box.width)) + MARGIN),
    height: Math.ceil(Math.max(...boxes.map((box) => box.y + box.height)) + MARGIN),
  };
}
