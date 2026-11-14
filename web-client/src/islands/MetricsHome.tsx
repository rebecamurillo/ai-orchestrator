/**
 * The Metrics home (story 4.2): this project's Runs to pick from, and every project's spend
 * this month. Both reads happen once on mount; nothing here is live, so it never subscribes
 * to `$poll`. The selection lives in the URL through `replaceState`, never a navigation.
 */
import { useEffect, useState } from 'react';

import { api } from '../api/client';
import type { components } from '../api/schema';
import FailedFetch from '../components/FailedFetch';
import MetricsRunsTable from '../components/metrics/MetricsRunsTable';
import OriginDrawer from '../components/metrics/OriginDrawer';
import SpendTable from '../components/metrics/SpendTable';
import {
  metricsHref,
  monthText,
  NO_PROJECT_LINE,
  pruneSelection,
  runRowView,
  toggleSelection,
} from '../lib/metrics/home';
import { loadCatalogue } from '../stores/catalogue';
import '../styles/metrics-home.css';

type MetricsRunOut = components['schemas']['MetricsRunOut'];
type ProjectSpendOut = components['schemas']['ProjectSpendOut'];

interface Props {
  projectId: string | null;
  projectName: string | null;
  select: string[];
}

type Phase<T> =
  { kind: 'loading' } | { kind: 'ready'; data: T } | { kind: 'error'; status: number | null };

export default function MetricsHome({ projectId, projectName, select }: Props) {
  const [runs, setRuns] = useState<Phase<MetricsRunOut[]>>({ kind: 'loading' });
  const [spend, setSpend] = useState<Phase<ProjectSpendOut[]>>({ kind: 'loading' });
  const [selected, setSelected] = useState<string[]>([]);
  const runsPath = `/metrics/runs?project=${projectId ?? ''}`;

  async function readRuns(): Promise<void> {
    if (!projectId) return;
    setRuns({ kind: 'loading' });
    try {
      const { data, error, response } = await api.GET('/metrics/runs', {
        params: { query: { project: projectId } },
      });
      if (error || !data) {
        setRuns({ kind: 'error', status: response.status });
        return;
      }
      setRuns({ kind: 'ready', data: data.items });
      setSelected(pruneSelection(select, data.items));
    } catch {
      setRuns({ kind: 'error', status: null });
    }
  }

  async function readSpend(): Promise<void> {
    setSpend({ kind: 'loading' });
    try {
      const { data, error, response } = await api.GET('/metrics/spend');
      if (error || !data) {
        setSpend({ kind: 'error', status: response.status });
        return;
      }
      setSpend({ kind: 'ready', data: data.items });
    } catch {
      setSpend({ kind: 'error', status: null });
    }
  }

  useEffect(() => {
    void loadCatalogue();
    void readSpend();
    void readRuns();
    // once on mount
  }, []);

  function change(next: string[]): void {
    setSelected(next);
    window.history.replaceState(null, '', metricsHref(projectId, next));
  }

  return (
    <>
      <section data-testid="metrics-runs">
        <h2 className="metrics-home-head">{projectName ? `RUNS · ${projectName}` : 'RUNS'}</h2>
        {!projectId ? (
          <p className="metrics-no-project" data-testid="metrics-no-project">
            {NO_PROJECT_LINE}
          </p>
        ) : runs.kind === 'error' ? (
          <FailedFetch
            method="GET"
            path={runsPath}
            status={runs.status}
            onRetry={() => void readRuns()}
            testId="metrics-runs-failed"
            retryTestId="metrics-runs-retry"
          />
        ) : runs.kind === 'ready' ? (
          <MetricsRunsTable
            rows={runs.data.map(runRowView)}
            selected={selected}
            onToggle={(id) => change(toggleSelection(selected, id))}
            onClear={() => change([])}
          />
        ) : null}
      </section>
      <section data-testid="metrics-spend">
        <h2 className="metrics-home-head">SPEND THIS MONTH · {monthText(new Date())}</h2>
        {spend.kind === 'error' ? (
          <FailedFetch
            method="GET"
            path="/metrics/spend"
            status={spend.status}
            onRetry={() => void readSpend()}
            testId="metrics-spend-failed"
            retryTestId="metrics-spend-retry"
          />
        ) : spend.kind === 'ready' ? (
          <SpendTable items={spend.data} projectId={projectId} />
        ) : null}
      </section>
      <OriginDrawer />
    </>
  );
}
