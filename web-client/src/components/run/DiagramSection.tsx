/**
 * The embedded run diagram (v3, 2026-09-24): fetch, expansion state, the bar above the
 * canvas, the column heads and the footer readout under it. The model is
 * `lib/diagram/run-tree.ts`, the placement is `lib/diagram/flow-layout.ts`, and the React
 * Flow element is `diagram/FlowCanvas.tsx` — this component owns only what has to touch the
 * network and the operator's state.
 *
 * `detail` is passed as a prop: `RunDetail` owns the polled detail fetch, so this section
 * never opens a second detail poll, and the failed-attempt join reads the steps that fetch
 * already returned. The graph is the separate, lazier datum — a graph-fetch error shows the
 * full-surface failed-request readout inside `wf-diagram-main` only, and the stop zone,
 * summary column and tab region keep rendering off the loaded `detail`.
 *
 * **The mount guard.** This section is a child of the `RunDetail` island, so `client:only`
 * cannot reach it and Astro renders it on the server. React Flow measures a DOM that is not
 * there; the skeleton stands in until the first `useEffect` has run, which is the browser.
 *
 * **A failing `/graph` is asked once, not every five seconds.** The island this replaced
 * called `stopPolling()`, which is the *shared* loop the Run detail runs on — stopping it
 * would take the whole surface's refresh down with the diagram's. So the poll effect skips
 * its own re-fetch while the phase is `error`, and the retry control is what asks again.
 *
 * **Expansion survives a poll, and follows the Run.** `expandedGroups` is state here. Every
 * time the *path to the current step* changes — a step starting on a Run opened while
 * queued, or the Run moving into another epic — that path's ancestors are **merged** in, so
 * the footer never names a step that is nowhere on the canvas. Merged, never replaced: what
 * the operator opened by hand stays open.
 *
 * **The column heads are nodes of the canvas** (`flow-layout.ts`), not a strip above it: the
 * columns live inside a pannable, scaled transform, and a static row would sit over the
 * wrong ones after the first pan.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';
import type { Edge, ReactFlowInstance } from '@xyflow/react';

import { api } from '../../api/client';
import type { components } from '../../api/schema';
import FailedFetch from '../FailedFetch';
import FlowCanvas, { type CardNode } from './diagram/FlowCanvas';
import { ageText } from '../../lib/board/format';
import { flowLayout } from '../../lib/diagram/flow-layout';
import {
  buildHierarchy,
  defaultExpanded,
  findCurrentStep,
  footerText,
  RUN_STATUS_WORD,
} from '../../lib/diagram/run-tree';
import { runToken, stateAgeSeconds, type RunDetailOut } from '../../lib/run/detail';
import { $poll } from '../../stores/poll';
import '../../styles/flow.css';

type RunGraphOut = components['schemas']['RunGraphOut'];

interface Props {
  runId: string;
  detail: RunDetailOut;
}

type Phase = { kind: 'loading' } | { kind: 'ready' } | { kind: 'error'; status: number | null };

export const EMPTY_PLAN_TEXT = 'no steps planned';

export default function DiagramSection({ runId, detail }: Props) {
  const [mounted, setMounted] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [graph, setGraph] = useState<RunGraphOut | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [resetCount, setResetCount] = useState(0);
  const [zoom, setZoom] = useState(1);
  const requestSeqRef = useRef(0);
  /** The ancestor path of the current step, as last seen — `null` before the first fetch. */
  const currentPathRef = useRef<string | null>(null);
  const instanceRef = useRef<ReactFlowInstance<CardNode, Edge> | null>(null);
  const pollTick = useStore($poll);
  const handledTickRef = useRef(pollTick);
  /** Read inside the poll effect so a phase change alone never re-fires it. */
  const phaseRef = useRef(phase.kind);

  const fetchGraph = useCallback(async (): Promise<void> => {
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
      // Open the path to the current step whenever that path changes — on the first fetch,
      // when a Run opened while `queued` starts its first step, and when the Run moves into
      // an epic the operator had closed. Merged into what is already open: a seeding that
      // replaced the set wiped every epic the operator had expanded by hand.
      const open = defaultExpanded(result.data);
      const signature = [...open].sort().join(',');
      if (signature !== currentPathRef.current) {
        currentPathRef.current = signature;
        if (open.size > 0) {
          setExpandedGroups((previous) => new Set([...previous, ...open]));
        }
      }
    } catch {
      if (seq !== requestSeqRef.current) return;
      setPhase({ kind: 'error', status: null });
    }
  }, [runId]);

  // Written in an effect, never in the render body: under React 19's concurrent rendering a
  // discarded render would otherwise leave the ref describing a phase that never committed,
  // and the poll effect reads it.
  useEffect(() => {
    phaseRef.current = phase.kind;
  }, [phase.kind]);

  // The mount guard: React Flow never renders server-side.
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    void fetchGraph();
    // Fetch once on mount; every later fetch is the poll effect below or the retry control.
  }, [fetchGraph]);

  useEffect(() => {
    if (pollTick === handledTickRef.current) return;
    handledTickRef.current = pollTick;
    if (phaseRef.current === 'error') return;
    void fetchGraph();
  }, [pollTick, fetchGraph]);

  const onToggle = useCallback((id: string) => {
    setExpandedGroups((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const onInit = useCallback((instance: ReactFlowInstance<CardNode, Edge>) => {
    instanceRef.current = instance;
  }, []);

  const hierarchy = useMemo(
    () => (graph === null ? null : buildHierarchy(graph, detail.steps, expandedGroups)),
    [graph, detail.steps, expandedGroups],
  );

  const layout = useMemo(() => (hierarchy === null ? null : flowLayout(hierarchy)), [hierarchy]);

  if (!mounted || phase.kind === 'loading') {
    return (
      <div className="wf-diagram-skeleton" role="status" aria-busy="true">
        <span className="wf-visually-hidden">loading the run diagram</span>
      </div>
    );
  }

  if (phase.kind === 'error') {
    return (
      <FailedFetch
        method="GET"
        path={`/api/runs/${runId}/graph`}
        status={phase.status}
        onRetry={() => void fetchGraph()}
      />
    );
  }

  if (graph === null || layout === null || hierarchy === null) return null;

  const token = runToken(detail.run, detail.alert);
  const currentNode = findCurrentStep(graph);
  const currentRow =
    currentNode === null
      ? null
      : (detail.steps.find((step) => step.path === currentNode.id) ?? null);
  const storiesDone = detail.stories.filter((story) => story.state === 'done').length;
  const footer = footerText(
    currentRow === null ? null : { seq: currentRow.seq, label: currentRow.label },
    { steps: detail.steps.length, storiesDone, stories: detail.stories.length },
    {
      word: RUN_STATUS_WORD[token] ?? token.toLowerCase(),
      age: ageText(stateAgeSeconds(detail, Date.now())),
    },
  );

  // the plan itself has no rows — not "the model drew nothing", which is a different fact
  // and would be a defect rather than a state (`buildHierarchy` draws a root for any row)
  if (graph.nodes.length === 0) {
    return (
      <div>
        <p className="wf-diagram-empty">{EMPTY_PLAN_TEXT}</p>
        <footer className="wf-diagram-footer" data-testid="wf-diagram-footer">
          {footer}
        </footer>
      </div>
    );
  }

  const stepsDone = detail.steps.filter((step) => step.status === 'done').length;

  return (
    <div>
      <div className="wf-flow-bar">
        <span className="wf-flow-head">DIAGRAM</span>
        <button
          type="button"
          className="wf-flow-ctl"
          data-testid="wf-diagram-fit"
          onClick={() => void instanceRef.current?.fitView()}
        >
          fit
        </button>
        <button
          type="button"
          className="wf-flow-ctl"
          data-testid="wf-diagram-reset"
          onClick={() => setResetCount((previous) => previous + 1)}
        >
          reset layout
        </button>
        <span className="wf-flow-zoom" data-testid="wf-diagram-zoom">
          {Math.round(zoom * 100)}%
        </span>
      </div>
      <FlowCanvas
        layout={layout}
        runId={runId}
        onToggle={onToggle}
        resetKey={`${resetCount}|${[...expandedGroups].sort().join(',')}`}
        onInit={onInit}
        onZoom={setZoom}
        label={`run ${detail.run.branch} · ${stepsDone}/${detail.steps.length} steps`}
      />
      <footer className="wf-diagram-footer" data-testid="wf-diagram-footer">
        {footer}
      </footer>
    </div>
  );
}
