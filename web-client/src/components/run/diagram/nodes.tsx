/**
 * The four cards of the v3 run diagram — root, epic, story, agent — per the anatomy of
 * `_bmad-output/designs/mockups/RunDiagram-v3.html`. The guardrail strip and the retry chips
 * live in `strips.tsx`; `flow-layout.ts` decides where any of it goes.
 *
 * Each card comes in two pieces on purpose. `…Card` is the markup and nothing else: no
 * React Flow and no context (cards write `focusFiles`/`openStepDrawer`; the agent card reads
 * `$stepDrawer` for its selection mark), so it renders under `renderToStaticMarkup` in the
 * `environment: 'node'` suite where every test-id and word token is asserted. `…Node` is the
 * React Flow node type: the same card between the handles an edge attaches to.
 *
 * **Handles are named**: an agent card has `in` on its left and `retry` on its right.
 *
 * **Click grammar** (EXPERIENCE-v1 §2.2, 2026-09-24): the card body is a drag handle, never
 * a link. *Open step* opens the step drawer and the caret expands; both are real
 * `<button>`s carrying `nodrag`, so a click on them is not the start of a drag. *Files* on epic
 * and story cards changes only the files focus (`stores/files-focus.ts`).
 *
 * **The card is the focusable thing.** `FlowCanvas` turns React Flow's own node focus off, so
 * Tab lands on the card — a labelled group announcing `{title} · {status word}` — then its
 * controls. Colour is never the sole carrier: the word token sits beside every border, and the
 * guardrail words are text.
 */
import { useStore } from '@nanostores/react';
import type { ReactNode } from 'react';
import { Handle, Position } from '@xyflow/react';

import type { FlowNodeData } from '../../../lib/diagram/flow-layout';
import { statusWord, type HierarchyNode } from '../../../lib/diagram/run-tree';
import { focusFiles } from '../../../stores/files-focus';
import { $stepDrawer, openStepDrawer } from '../../../stores/step-drawer';
import { GuardrailStrip, RetryCard, RetryMoreCard } from './strips';

export interface CardProps {
  node: HierarchyNode;
  /** Still passed by `FlowCanvas`; unread now that the step page sits behind the drawer. */
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

/** The step page is one click further, through the drawer's `full page` (EXPERIENCE § 12 delta 4). */
function OpenStep({ node }: { node: HierarchyNode }) {
  if (!node.joined || node.seq === null) return null;
  const id = `wf-open-step-${node.path}`;
  return (
    <button
      type="button"
      className="wf-node-cta nodrag"
      id={id}
      data-testid={`wf-diagram-open-${node.path}`}
      onClick={() => openStepDrawer(node.seq!, node.attemptN, id)}
    >
      Open step
    </button>
  );
}

function Head({ node, onToggle }: { node: HierarchyNode; onToggle?: (id: string) => void }) {
  return (
    <div className="wf-node-head">
      {onToggle === undefined ? null : <Caret node={node} onToggle={onToggle} />}
      <span className="wf-node-eyebrow" data-now={node.current}>
        {node.eyebrow}
      </span>
      {onToggle === undefined ? null : (
        <button
          type="button"
          className="wf-node-files nodrag"
          data-testid={`wf-diagram-files-${node.path}`}
          aria-label={`files of ${node.title}`}
          onClick={() => focusFiles(node.id)}
        >
          Files
        </button>
      )}
      <Token token={node.token} />
    </div>
  );
}

function Shell({
  node,
  selected = false,
  children,
}: {
  node: HierarchyNode;
  selected?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={selected ? 'wf-node wf-node-selected' : 'wf-node'}
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
      {/* a frame-less Run's `plan`, `checkout` and `submodules` rows own no frame and live here */}
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

export function AgentCard({ node }: Omit<CardProps, 'onToggle'>) {
  const open = useStore($stepDrawer);
  return (
    <Shell node={node} selected={open !== null && open.seq === node.seq}>
      <Head node={node} />
      <p className="wf-node-title" title={node.title}>
        {node.title}
      </p>
      <p className="wf-node-meta" title={node.meta}>
        {node.meta}
      </p>
      <div className="wf-node-ctarow">
        <span className="wf-node-duration">{node.duration}</span>
        <OpenStep node={node} />
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
