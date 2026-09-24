/**
 * The `<ReactFlow>` element of the v3 run diagram, and nothing else — the fetch and the
 * expansion state are `DiagramSection`'s, the maths is `lib/diagram/flow-layout.ts`'s.
 *
 * **Drag is session-only** (EXPERIENCE-v1 §2.2, decision 21c). Positions live in this
 * component's own state, never on the server and never in storage: a poll re-computes the
 * layout, and `mergePositions` swaps each card's *data* while keeping the position the
 * operator put it in. A reload restores the computed tree — so a run whose plan grows
 * mid-flight never leaves an orphaned card.
 *
 * `resetKey` is what says *this is not a poll*: the caller changes it when the operator
 * presses *reset layout*, and when an expand or collapse changes the shape of the tree.
 * Keeping the old positions through an expansion would drop the newly revealed children on
 * top of the cards that were already placed — the tree the operator opened is a different
 * tree, and it is drawn as one.
 *
 * `nodeTypes` is defined at module scope on purpose: React Flow re-creates every node when
 * that object's identity changes, which would drop the drag positions on every poll tick.
 *
 * **The card is the focusable thing, not React Flow's wrapper** (`nodesFocusable={false}`):
 * the wrapper announces `aria-roledescription="node"` and nothing about the run, while the
 * card is already a labelled group saying `{title} · {status word}`. One stop per card, and
 * the controls inside it next, in reading order.
 *
 * Nothing here is connectable and nothing here draws a new edge — the graph is a read of the
 * plan. The attribution watermark stays visible (React Flow is MIT and asks for it).
 */
import { useCallback, useEffect, useRef } from 'react';
import {
  ReactFlow,
  useNodesState,
  type Edge,
  type Node,
  type NodeTypes,
  type ReactFlowInstance,
  type Viewport,
} from '@xyflow/react';

import type { FlowLayout, FlowNodeType } from '../../../lib/diagram/flow-layout';
import { AgentNode, EpicNode, HeadNode, MoreNode, RetryNode, RootNode, StoryNode } from './nodes';
import '@xyflow/react/dist/base.css';
import '../../../styles/flow.css';

/**
 * Module scope: a new object here would re-mount every card on every poll tick.
 *
 * React Flow types the map over its own `NodeProps<Node>`, whose `data` is an open
 * `Record<string, unknown>`; these cards take the closed union `FlowNodeData` and narrow it,
 * and a component that accepts less than the library promises to pass is not assignable
 * under `strictFunctionTypes`. The one cast in this file is that library-typing gap, and it
 * buys the narrowing that removed every `data.node!` assertion from `nodes.tsx`.
 */
export const nodeTypes = {
  runHead: HeadNode,
  runRoot: RootNode,
  runEpic: EpicNode,
  runStory: StoryNode,
  runAgent: AgentNode,
  runRetry: RetryNode,
  runMore: MoreNode,
} as unknown as NodeTypes;

/** What a card is handed once `DiagramSection`'s two values are folded into the layout's. */
export type CardData = FlowLayout['nodes'][number]['data'] & {
  runId: string;
  onToggle: (id: string) => void;
};

export type CardNode = Node<CardData, FlowNodeType>;

interface Props {
  layout: FlowLayout;
  runId: string;
  onToggle: (id: string) => void;
  /** Changes on *reset layout* and on every expand or collapse; never on a poll. */
  resetKey: string;
  onInit: (instance: ReactFlowInstance<CardNode, Edge>) => void;
  onZoom: (zoom: number) => void;
  label: string;
}

/** The layout's nodes with the two values the cards need folded into their `data`. */
export function withHandlers(
  layout: FlowLayout,
  runId: string,
  onToggle: (id: string) => void,
): CardNode[] {
  return layout.nodes.map((node) => ({ ...node, data: { ...node.data, runId, onToggle } }));
}

/**
 * The next node list: freshly computed data, at the positions the operator left the cards at.
 *
 * `reset` throws those positions away — the control was pressed, or the tree changed shape.
 * A node the previous list did not hold takes its computed place either way, which is what
 * lets a plan grow mid-run without the new cards landing at the origin.
 */
export function mergePositions(
  previous: CardNode[],
  computed: CardNode[],
  reset: boolean,
): CardNode[] {
  if (reset) return computed;
  const placed = new Map(previous.map((node) => [node.id, node.position]));
  return computed.map((node) => {
    const position = placed.get(node.id);
    return position === undefined ? node : { ...node, position };
  });
}

export default function FlowCanvas({
  layout,
  runId,
  onToggle,
  resetKey,
  onInit,
  onZoom,
  label,
}: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<CardNode>(
    withHandlers(layout, runId, onToggle),
  );
  const resetRef = useRef(resetKey);

  useEffect(() => {
    const computed = withHandlers(layout, runId, onToggle);
    const reset = resetRef.current !== resetKey;
    resetRef.current = resetKey;
    setNodes((previous) => mergePositions(previous, computed, reset));
  }, [layout, runId, onToggle, resetKey, setNodes]);

  // `onMove` fires on every pan frame; the readout only ever shows the zoom, so a pan must
  // not re-render the section that owns it
  const zoomRef = useRef<number | null>(null);
  const handleMove = useCallback(
    (_event: MouseEvent | TouchEvent | null, viewport: Viewport) => {
      if (zoomRef.current === viewport.zoom) return;
      zoomRef.current = viewport.zoom;
      onZoom(viewport.zoom);
    },
    [onZoom],
  );

  const frameRef = useRef(0);
  useEffect(() => () => cancelAnimationFrame(frameRef.current), []);

  // `fitView` runs on mount, so the readout's own initial `100%` would be a figure the canvas
  // never showed. Seed it from the instance the moment there is one, and again on the next
  // frame — `onInit` fires before the initial fit has been applied, so the first read is the
  // default viewport and the second is the one the operator is looking at.
  const handleInit = useCallback(
    (instance: ReactFlowInstance<CardNode, Edge>) => {
      handleMove(null, instance.getViewport());
      frameRef.current = requestAnimationFrame(() => handleMove(null, instance.getViewport()));
      onInit(instance);
    },
    [onInit, handleMove],
  );

  return (
    <div className="wf-flow" data-testid="wf-diagram" role="group" aria-label={label}>
      <ReactFlow<CardNode, Edge>
        nodes={nodes}
        edges={layout.edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onInit={handleInit}
        onMove={handleMove}
        nodesConnectable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        elementsSelectable={false}
        preventScrolling={false}
        proOptions={{ hideAttribution: false }}
        fitView
        minZoom={0.2}
        maxZoom={1.5}
      />
    </div>
  );
}
