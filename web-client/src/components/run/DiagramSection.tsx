/**
 * The embedded run diagram (story 1-4): fetches `GET /runs/{id}/graph` independently of the
 * RunDetail poll, collapses the result into the four-column tree, and renders the SVG in-place.
 *
 * `detail` is passed as a prop — RunDetail owns the polled detail fetch and passes it down so
 * DiagramSection does not open a second detail poll. The graph is a separate, lazier datum:
 * a graph-fetch error shows `fetch-failed` inside `wf-diagram-main` only; the stop zone,
 * summary column, and tab region continue to render off the already-loaded `detail` prop.
 *
 * Node clicks navigate to `?view=detail#step-{seq}`: the `?view=detail` prefix ensures the
 * same page + step fragment is served whether the user arrived via redirect or directly.
 *
 * `window.location.assign('#step-{seq}')` (hash-only) was the original design-note intent, but
 * the frozen e2e test `run-diagram.spec.ts` (c) checks for `?view=detail#step-\d+` in the URL
 * post-click, so the `?view=detail` prefix is kept to satisfy the frozen assertion.
 */
import { useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../../api/client';
import type { components } from '../../api/schema';
import FailedFetch from '../FailedFetch';
import { ageText } from '../../lib/board/format';
import { layoutGraph } from '../../lib/diagram/layout';
import { DiagramEdge, DiagramGroup, DiagramNode } from '../../lib/diagram/svg';
import { buildRunTree, findCurrentStep } from '../../lib/diagram/tree';
import {
  runToken,
  stateAgeSeconds,
  type RunDetailOut,
  type StepRowOut,
} from '../../lib/run/detail';
import '../../styles/diagram.css';

type RunGraphOut = components['schemas']['RunGraphOut'];
type RunNodeOut = components['schemas']['RunNodeOut'];
type RunGroupOut = components['schemas']['RunGroupOut'];
type NodeOut = components['schemas']['NodeOut'];
type GroupOut = components['schemas']['GroupOut'];

interface Props {
  runId: string;
  detail: RunDetailOut;
}

type Phase = { kind: 'loading' } | { kind: 'ready' } | { kind: 'error'; status: number | null };

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

function nodeSeq(nodeId: string, steps: StepRowOut[]): number | null {
  const exact = steps.find((s) => s.path === nodeId);
  if (exact) return exact.seq;
  const prefix = steps.find((s) => s.path.startsWith(`${nodeId}/`));
  return prefix?.seq ?? null;
}

function pathLabel(id: string): string {
  return id
    .split('/')
    .map((segment) => segment.replace('-', ' '))
    .join(' · ');
}

export default function DiagramSection({ runId, detail }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [graph, setGraph] = useState<RunGraphOut | null>(null);
  const requestSeqRef = useRef(0);

  async function fetchGraph(): Promise<void> {
    const seq = ++requestSeqRef.current;
    try {
      const result = await api.GET('/runs/{run_id}/graph', {
        params: { path: { run_id: runId } },
      });
      if (seq !== requestSeqRef.current) return;
      if (result.error || !result.data) {
        setPhase({ kind: 'error', status: result.response?.status ?? null });
        return;
      }
      setGraph(result.data);
      setPhase({ kind: 'ready' });
    } catch {
      if (seq !== requestSeqRef.current) return;
      setPhase({ kind: 'error', status: null });
    }
  }

  useEffect(() => {
    void fetchGraph();
    // Fetch once on mount; retry only via the FailedFetch button.
  }, [runId]);

  const tree = useMemo(() => (graph ? buildRunTree(graph) : null), [graph]);

  const layout = useMemo(() => {
    if (!tree) return null;
    return layoutGraph(tree as { nodes: NodeOut[]; edges: typeof tree.edges; groups: GroupOut[] });
  }, [tree]);

  if (phase.kind === 'loading') {
    return <div className="wf-diagram-skeleton" aria-busy="true" />;
  }

  if (phase.kind === 'error') {
    return (
      <FailedFetch
        method="GET"
        path={`/api/runs/${runId}/graph`}
        status={(phase as { kind: 'error'; status: number | null }).status}
        onRetry={() => void fetchGraph()}
      />
    );
  }

  if (!graph || !layout) return null;

  const token = runToken(detail.run, detail.alert);
  const now = Date.now();
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
    <div>
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
