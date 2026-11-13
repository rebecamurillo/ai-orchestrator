/**
 * The comparison page (story 4.3): the API's `/metrics/compare` payload as a grid. Runs,
 * result versions and blind change the payload and re-request it; the metric set and the view
 * only re-render. The state lives in the URL through `replaceState`, never a navigation, and
 * nothing here is live, so it never subscribes to `$poll`.
 */
import { useEffect, useRef, useState } from 'react';

import { useStore } from '@nanostores/react';

import { api } from '../api/client';
import type { components } from '../api/schema';
import CompareCharts from '../components/charts/CompareCharts';
import FailedFetch from '../components/FailedFetch';
import CompareBar from '../components/metrics/CompareBar';
import CompareGrid from '../components/metrics/CompareGrid';
import OriginDrawer from '../components/metrics/OriginDrawer';
import {
  compareQuery,
  compareSearch,
  removeRun,
  setVersion,
  TOO_FEW_LINE,
  type CompareState,
} from '../lib/metrics/compare';
import { exportComparison } from '../lib/metrics/compare-export';
import { $catalogue, loadCatalogue } from '../stores/catalogue';
import '../styles/metrics-compare.css';

type CompareOut = components['schemas']['CompareOut'];

type Phase =
  | { kind: 'loading' }
  | { kind: 'ready'; payload: CompareOut }
  | { kind: 'error'; status: number | null };

export default function MetricsCompare({ initial }: { initial: CompareState }) {
  const [state, setState] = useState<CompareState>(initial);
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [exportLine, setExportLine] = useState('');
  const [projectId, setProjectId] = useState<string | null>(null);
  const [stepOrder, setStepOrder] = useState<string[]>([]);
  const { entries } = useStore($catalogue);
  const latest = useRef(0);
  const orders = useRef(new Map<string, string[]>());
  const firstRun = phase.kind === 'ready' ? phase.payload.runs[0]?.run_id : undefined;
  const tooFew = state.runIds.length < 2;
  const key = JSON.stringify(compareQuery(state));

  async function read(): Promise<void> {
    latest.current += 1;
    const mine = latest.current;
    setPhase({ kind: 'loading' });
    try {
      const { data, error, response } = await api.GET('/metrics/compare', {
        params: { query: compareQuery(state) },
      });
      if (mine !== latest.current) return;
      if (error || !data) setPhase({ kind: 'error', status: response.status });
      else {
        setProjectId(data.project_id);
        setPhase({ kind: 'ready', payload: data });
      }
    } catch {
      if (mine === latest.current) setPhase({ kind: 'error', status: null });
    }
  }

  useEffect(() => {
    void loadCatalogue();
  }, []);

  useEffect(() => {
    if (!tooFew) void read();
    // the payload follows the query, not the layout state
  }, [key]);

  useEffect(() => {
    if (state.view !== 'chart' || firstRun === undefined) return;
    // a compare re-read (blind, version) passes firstRun through undefined: keep its order
    const known = orders.current.get(firstRun);
    if (known !== undefined) {
      setStepOrder(known);
      return;
    }
    let current = true;
    void (async () => {
      let order: string[] = [];
      try {
        const { data } = await api.GET('/runs/{run_id}/detail', {
          params: { path: { run_id: firstRun } },
        });
        if (data) order = [...data.steps].sort((a, b) => a.seq - b.seq).map((st) => st.path);
      } catch {
        order = [];
      }
      orders.current.set(firstRun, order);
      if (current) setStepOrder(order);
    })();
    return () => {
      current = false;
    };
    // the detail only orders roles: one read per first Run while CHART is shown
  }, [state.view, firstRun]);

  function change(next: CompareState): void {
    setState(next);
    window.history.replaceState(null, '', `/metrics/compare${compareSearch(next)}`);
  }

  async function runExport(): Promise<void> {
    if (phase.kind !== 'ready') return;
    const result = await exportComparison(state, phase.payload.project_name);
    setExportLine(result.line);
  }

  if (tooFew) {
    return (
      <p className="compare-too-few" data-testid="compare-too-few">
        {TOO_FEW_LINE} · <a href="/metrics">Metrics</a>
      </p>
    );
  }

  return (
    <>
      {projectId !== null && (
        <CompareBar
          state={state}
          projectId={projectId}
          onChange={change}
          onExport={() => void runExport()}
          exportLine={exportLine}
        />
      )}
      {phase.kind === 'error' ? (
        <FailedFetch
          method="GET"
          path="/api/metrics/compare"
          status={phase.status}
          onRetry={() => void read()}
          testId="compare-failed"
          retryTestId="compare-retry"
        />
      ) : (
        phase.kind === 'ready' &&
        (state.view === 'chart' ? (
          <CompareCharts
            payload={phase.payload}
            entries={entries}
            set={state.set}
            stepOrder={stepOrder}
          />
        ) : (
          <CompareGrid
            payload={phase.payload}
            set={state.set}
            onRemove={(id) => change(removeRun(state, id))}
            onVersion={(id, n, top) => change(setVersion(state, id, n, top))}
          />
        ))
      )}
      <OriginDrawer />
    </>
  );
}
