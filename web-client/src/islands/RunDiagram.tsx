/**
 * The Run diagram island (8.1): polls `GET /runs/{id}/detail` and `GET /runs/{id}/graph`,
 * collapses the graph into the four-column tree via `buildRunTree`, lays it out with
 * `layoutGraph`, and renders the DIAGRAM view of a Run.
 *
 * Mirrors `RunDetail.tsx`'s poll pattern exactly: one `requestSeqRef` staleness guard,
 * `$poll`/`configurePolling`/`stopPolling` from the shared store, and a Promise.all for
 * the two fetches so a single tick drives both.
 *
 * Status has two writers (AD-8): this island never writes or derives Run/Step status —
 * everything shown here comes verbatim off the API responses.
 *
 * Node clicks navigate to `?view=detail#step-{seq}` via `window.location.assign`, which
 * re-mounts `RunDetail` with the correct fragment anchor.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import { api } from '../api/client';
import type { components } from '../api/schema';
import FailedFetch from '../components/FailedFetch';
import Banner from '../components/run/Banner';
import Header from '../components/run/Header';
import { layoutGraph } from '../lib/diagram/layout';
import { DiagramEdge, DiagramGroup, DiagramNode } from '../lib/diagram/svg';
import { ageText } from '../lib/board/format';
import { buildRunTree, findCurrentStep } from '../lib/diagram/tree';
import { runToken, stateAgeSeconds, type RunDetailOut, type StepRowOut } from '../lib/run/detail';
import { $poll, configurePolling, stopPolling } from '../stores/poll';
import '../styles/run-detail.css';
import '../styles/diagram.css';

type RunGraphOut = components['schemas']['RunGraphOut'];
type RunNodeOut = components['schemas']['RunNodeOut'];
type RunGroupOut = components['schemas']['RunGroupOut'];
type NodeOut = components['schemas']['NodeOut'];
type GroupOut = components['schemas']['GroupOut'];

interface Props {
  runId: string;
}

type Phase = { kind: 'loading' } | { kind: 'ready' } | { kind: 'error'; status: number | null };

/** Map a Run token to a lower-case status word for the footer. */
const TOKEN_WORD: Record<string, string> = {
  QUE: 'queued',
  RUN: 'running',
  BLK: 'blocked',
  CHK: 'checkpoint',
  DON: 'done',
  ERR: 'failed',
  CAN: 'cancelled',
  SKP: 'skipped',
};

/**
 * The seq of the first `detail.steps` row whose path is or starts with `nodeId`.
 * Exact match first (for plain step nodes), then prefix match (for story aggregate nodes).
 */
function nodeSeq(nodeId: string, steps: StepRowOut[]): number | null {
  const exact = steps.find((s) => s.path === nodeId);
  if (exact) return exact.seq;
  const prefix = steps.find((s) => s.path.startsWith(`${nodeId}/`));
  return prefix?.seq ?? null;
}

/**
 * Human-readable path label from a step id: `epic-2/story-4-1/build` →
 * `epic 2 · story 4-1 · build`. Each segment has its first hyphen replaced with a space so
 * `epic-2` reads `epic 2` and `story-4-1` reads `story 4-1`; the rest of the id is kept
 * as-is so the story identifier's own hyphens survive.
 */
function pathLabel(id: string): string {
  return id
    .split('/')
    .map((segment) => segment.replace('-', ' '))
    .join(' · ');
}

export default function RunDiagram({ runId }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [detail, setDetail] = useState<RunDetailOut | null>(null);
  const [graph, setGraph] = useState<RunGraphOut | null>(null);
  const pollTick = useStore($poll);
  const requestSeqRef = useRef(0);
  const mountedTickRef = useRef(pollTick);

  async function fetchBoth(): Promise<void> {
    const seq = ++requestSeqRef.current;
    try {
      const [detailResult, graphResult] = await Promise.all([
        api.GET('/runs/{run_id}/detail', { params: { path: { run_id: runId } } }),
        api.GET('/runs/{run_id}/graph', { params: { path: { run_id: runId } } }),
      ]);
      if (seq !== requestSeqRef.current) return;

      if (detailResult.error || !detailResult.data) {
        stopPolling();
        setPhase({ kind: 'error', status: detailResult.response?.status ?? null });
        return;
      }
      if (graphResult.error || !graphResult.data) {
        stopPolling();
        setPhase({ kind: 'error', status: graphResult.response?.status ?? null });
        return;
      }

      setDetail(detailResult.data);
      setGraph(graphResult.data);
      setPhase({ kind: 'ready' });
      configurePolling(detailResult.data.run.status === 'running');
    } catch {
      if (seq !== requestSeqRef.current) return;
      stopPolling();
      setPhase({ kind: 'error', status: null });
    }
  }

  useEffect(() => {
    void fetchBoth();
    return () => stopPolling();
    // fires once on mount; every later fetch is driven by the `$poll` effect below
  }, [runId]);

  useEffect(() => {
    if (pollTick === mountedTickRef.current) return;
    void fetchBoth();
  }, [pollTick]);

  const tree = useMemo(() => {
    if (!graph) return null;
    return buildRunTree(graph);
  }, [graph]);

  const layout = useMemo(() => {
    if (!tree) return null;
    // RunNodeOut/RunGroupOut structurally extend NodeOut/GroupOut (all required fields present)
    return layoutGraph(tree as { nodes: NodeOut[]; edges: typeof tree.edges; groups: GroupOut[] });
  }, [tree]);

  if (phase.kind === 'error') {
    return (
      <FailedFetch
        method="GET"
        path={`/api/runs/${runId}/graph`}
        status={phase.status}
        onRetry={() => void fetchBoth()}
      />
    );
  }

  if (!detail || !graph || !layout) return null;

  const token = runToken(detail.run, detail.alert);
  const now = Date.now();

  // Footer: current step info
  const currentStep = findCurrentStep(graph);
  const totalSteps = detail.steps.length;
  const currentStepRow = currentStep
    ? (detail.steps.find((s) => s.path === currentStep.id) ?? null)
    : null;
  const seq = currentStepRow?.seq;

  const storiesDone = detail.stories.filter((s) => s.state === 'done').length;
  const storiesTotal = detail.stories.length;

  const statusWord = TOKEN_WORD[token] ?? token.toLowerCase();
  const age = ageText(stateAgeSeconds(detail, now));

  const footerText =
    currentStep !== null && seq !== undefined
      ? `step ${seq} of ${totalSteps} · ${pathLabel(currentStep.id)} · ${statusWord} ${age} · ${storiesDone}/${storiesTotal} stories`
      : `${storiesDone}/${storiesTotal} stories`;

  const stepsDone = detail.steps.filter((s) => s.status === 'done').length;

  return (
    <div data-testid="wf-detail">
      <Header detail={detail} token={token} now={now} view="diagram" />
      <Banner detail={detail} token={token} />
      <div className="wf-diagram-heads">
        <span>RUN</span>
        <span>EPICS</span>
        <span>STORIES</span>
        <span>STEPS</span>
      </div>
      <div
        data-testid="wf-diagram"
        role="img"
        aria-label={`run ${detail.run.branch} · ${stepsDone}/${totalSteps} steps`}
      >
        <svg
          className="diagram-svg"
          width={layout.width}
          height={layout.height}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
        >
          {/* groups first, so the dashed rectangle sits behind the boxes it encloses */}
          {layout.groups.map((placed) => {
            const runGroup = placed.group as RunGroupOut;
            return <DiagramGroup key={placed.group.id} placed={placed} status={runGroup.status} />;
          })}
          {layout.edges.map((placed) => (
            <DiagramEdge key={placed.id} placed={placed} />
          ))}
          {layout.nodes.map((placed) => {
            const runNode = placed.node as RunNodeOut & { substeps?: string[] };
            const stepSeq = nodeSeq(placed.node.id, detail.steps);
            return (
              <DiagramNode
                key={placed.node.id}
                placed={placed}
                status={runNode.status}
                token={runNode.token}
                current={runNode.current}
                substeps={runNode.substeps}
                onClick={
                  stepSeq !== null
                    ? () => window.location.assign(`?view=detail#step-${stepSeq}`)
                    : undefined
                }
              />
            );
          })}
        </svg>
      </div>
      <footer data-testid="wf-diagram-footer">{footerText}</footer>
    </div>
  );
}
