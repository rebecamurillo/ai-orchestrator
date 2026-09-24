/**
 * The four cards of the v3 run diagram — root, epic, story, agent — per the anatomy of
 * `_bmad-output/designs/mockups/RunDiagram-v3.html`. The guardrail strip and the retry chips
 * live in `strips.tsx`; `flow-layout.ts` decides where any of it goes.
 *
 * Each card comes in two pieces on purpose. `…Card` is the markup and nothing else: no
 * React Flow, no store, no context, so it renders under `renderToStaticMarkup` in the
 * `environment: 'node'` suite where every test-id and word token is asserted. `…Node` is the
 * React Flow node type: the same card between the handles an edge attaches to, narrowing the
 * discriminated `FlowNodeData` rather than asserting what it was handed.
 *
 * **Handles are named** because an agent card carries two targets — `in` on its left, where
 * its story joins it, and `retry` on its right, where a chip in the attempts gutter loops
 * back into it (`lib/diagram/flow-layout.ts` writes the matching edge).
 *
 * **Click grammar** (EXPERIENCE-v1 §2.2, 2026-09-24): the card body is a drag handle, never
 * a link. The only navigation is the *Open step* CTA, and the only state change is the
 * expand caret; both are real `<button>`s and both carry `nodrag` so a click on them is a
 * click and not the start of a drag.
 *
 * **The card is the focusable thing.** `FlowCanvas` turns React Flow's own node focus off, so
 * Tab lands on the card itself — a labelled group announcing `{title} · {status word}` — and
 * then on the controls inside it, in reading order. Colour is never the sole carrier: the
 * word token sits beside every border, and the guardrail words are text.
 */
import type { ReactNode } from 'react';
import { Handle, Position } from '@xyflow/react';

import type { FlowNodeData } from '../../../lib/diagram/flow-layout';
import { statusWord, type HierarchyNode } from '../../../lib/diagram/run-tree';
import { GuardrailStrip, RetryCard, RetryMoreCard } from './strips';

export interface CardProps {
  node: HierarchyNode;
  /** `/workflows/{runId}/steps/{path}` is built here, so the card needs the Run. */
  runId: string;
  onToggle: (id: string) => void;
}

function Token({ token }: { token: string | null }) {
  if (token === null) return null;
  return (
    <span className="wf-node-token" data-token={token}>
      {token}
    </span>
  );
}

/** The epic/story caret: one level per click, `aria-expanded` on a real button. */
function Caret({ node, onToggle }: { node: HierarchyNode; onToggle: (id: string) => void }) {
  if (!node.expandable) return null;
  return (
    <button
      type="button"
      className="wf-node-caret nodrag"
      data-testid={`wf-diagram-toggle-${node.path}`}
      aria-expanded={node.expanded}
      aria-label={`${node.expanded ? 'collapse' : 'expand'} ${node.title}`}
      onClick={() => onToggle(node.id)}
    >
      {node.expanded ? '▾' : '▸'}
    </button>
  );
}

/**
 * The one explicit navigation on the surface; omitted when no step row joins the node.
 *
 * A real link, not a button that assigns `location`: middle-click, cmd-click, *open in new
 * tab*, *copy link address* and the status-bar URL preview are all things the leaf-node
 * navigation this replaced already had, and a `<button>` takes every one of them away.
 * "The card body is a drag handle, never a link" is satisfied by a link *inside* the card —
 * which is what `nodrag` marks: a click here is a click, not the start of a drag.
 */
function OpenStep({ node, runId }: { node: HierarchyNode; runId: string }) {
  if (!node.joined) return null;
  return (
    <a
      className="wf-node-cta nodrag"
      data-testid={`wf-diagram-open-${node.path}`}
      href={`/workflows/${runId}/steps/${node.path}`}
    >
      Open step
    </a>
  );
}

function Head({ node, onToggle }: { node: HierarchyNode; onToggle?: (id: string) => void }) {
  return (
    <div className="wf-node-head">
      {onToggle === undefined ? null : <Caret node={node} onToggle={onToggle} />}
      <span className="wf-node-eyebrow" data-now={node.current}>
        {node.eyebrow}
      </span>
      <Token token={node.token} />
    </div>
  );
}

function Shell({ node, children }: { node: HierarchyNode; children: ReactNode }) {
  return (
    <div
      className="wf-node"
      data-testid={`wf-diagram-node-${node.path}`}
      data-kind={node.kind}
      data-rank={node.rank}
      data-status={node.border}
      data-current={node.current}
      role="group"
      tabIndex={0}
      // the current step and a merely-running ancestor both read `RUN`; the name says which
      aria-label={
        `${node.title} · ${statusWord(node.token)}` +
        (node.current
          ? ' · current step'
          : node.border === 'inflight'
            ? ' · holds the current step'
            : '')
      }
    >
      {children}
    </div>
  );
}

export function RootCard({ node }: { node: HierarchyNode }) {
  return (
    <Shell node={node}>
      <Head node={node} />
      <p className="wf-node-title" title={node.title}>
        {node.title}
      </p>
      <p className="wf-node-meta" title={node.meta}>
        {node.meta}
      </p>
      {/* a frame-less Run's `plan`, `checkout` and `submodules` rows own no frame and live
          here — built without a renderer, they vanished (operator amendment, 2026-09-24) */}
      <GuardrailStrip strip={node.guardrail} />
    </Shell>
  );
}

export function EpicCard({ node, onToggle }: Omit<CardProps, 'runId'>) {
  return (
    <Shell node={node}>
      <Head node={node} onToggle={onToggle} />
      <p className="wf-node-title" title={node.title}>
        {node.title}
      </p>
      <p className="wf-node-meta" title={node.meta}>
        {node.meta}
      </p>
      <GuardrailStrip strip={node.guardrail} />
    </Shell>
  );
}

export function StoryCard({ node, onToggle }: Omit<CardProps, 'runId'>) {
  return (
    <Shell node={node}>
      <Head node={node} onToggle={onToggle} />
      <p className="wf-node-title" title={node.title}>
        {node.title}
      </p>
      <GuardrailStrip strip={node.guardrail} />
    </Shell>
  );
}

export function AgentCard({ node, runId }: Omit<CardProps, 'onToggle'>) {
  return (
    <Shell node={node}>
      <Head node={node} />
      <p className="wf-node-title" title={node.title}>
        {node.title}
      </p>
      <p className="wf-node-meta" title={node.meta}>
        {node.meta}
      </p>
      <div className="wf-node-ctarow">
        <span className="wf-node-duration">{node.duration}</span>
        <OpenStep node={node} runId={runId} />
      </div>
    </Shell>
  );
}

/** What React Flow hands a node type, narrowed to what these cards read. */
export interface NodeProps {
  data: FlowNodeData & { runId: string; onToggle: (id: string) => void };
}

function In() {
  return <Handle type="target" position={Position.Left} id="in" isConnectable={false} />;
}

function Out() {
  return <Handle type="source" position={Position.Right} id="out" isConnectable={false} />;
}

function Back() {
  return <Handle type="source" position={Position.Left} id="back" isConnectable={false} />;
}

export function RootNode({ data }: NodeProps) {
  if (data.kind !== 'card') return null;
  return (
    <>
      <RootCard node={data.node} />
      <Out />
    </>
  );
}

export function EpicNode({ data }: NodeProps) {
  if (data.kind !== 'card') return null;
  return (
    <>
      <In />
      <EpicCard node={data.node} onToggle={data.onToggle} />
      <Out />
    </>
  );
}

export function StoryNode({ data }: NodeProps) {
  if (data.kind !== 'card') return null;
  return (
    <>
      <In />
      <StoryCard node={data.node} onToggle={data.onToggle} />
      <Out />
    </>
  );
}

export function AgentNode({ data }: NodeProps) {
  if (data.kind !== 'card') return null;
  return (
    <>
      <In />
      <AgentCard node={data.node} runId={data.runId} />
      <Handle type="target" position={Position.Right} id="retry" isConnectable={false} />
    </>
  );
}

export function RetryNode({ data }: NodeProps) {
  if (data.kind !== 'chip') return null;
  return (
    <>
      <Back />
      <RetryCard chip={data.chip} ownerPath={data.ownerPath} />
    </>
  );
}

export function MoreNode({ data }: NodeProps) {
  if (data.kind !== 'more') return null;
  return (
    <>
      <Back />
      <RetryMoreCard overflow={data.overflow} ownerPath={data.ownerPath} />
    </>
  );
}

/**
 * A column head, inside the canvas transform so it pans and zooms with the column it names.
 *
 * `aria-hidden`: every card under it already announces what it is, and a screen reader
 * reading `EPICS` as a node of the graph would be reading the furniture.
 */
export function HeadNode({ data }: NodeProps) {
  if (data.kind !== 'head') return null;
  return (
    <span
      className="wf-flow-head-node"
      data-testid={`wf-diagram-head-${data.rank}`}
      aria-hidden="true"
    >
      {data.label}
    </span>
  );
}
