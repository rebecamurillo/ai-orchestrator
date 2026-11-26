/**
 * The selected auto workflow: with a Run, its summary and a link to the workflow's own page;
 * without one, when it starts and the project defaults. `RunSummaryOut` carries no current-step
 * label or progress, so the workflow's own API token and line stand in for them.
 */
import { useEffect, useState } from 'react';

import type { components } from '../../api/schema';
import { api } from '../../api/client';
import { tokenSignal } from '../../lib/board/format';
import { notStartedLines, type DetailWorkflow } from '../../lib/initiative/page';
import FailedFetch from '../FailedFetch';

type RunSummary = components['schemas']['RunSummaryOut'];
type Project = components['schemas']['ProjectRead'];

interface Props {
  workflow: DetailWorkflow;
  previous: string | null;
  projectId: string | null;
}

type Loaded =
  | { kind: 'loading' }
  | { kind: 'error'; path: string; status: number | null }
  | { kind: 'run'; run: RunSummary }
  | { kind: 'project'; project: Project | null };

const FIXED_LINE =
  "The diagram, the steps, the logs and the files per epic and story are on the workflow's own page. A stop of this workflow shows here as needs you, with its reason, and is answered there.";

export default function AutoWorkflowSummary({ workflow, previous, projectId }: Props) {
  const [state, setState] = useState<Loaded>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const runId = workflow.run_id;

  useEffect(() => {
    let live = true;
    const path = runId ? `/api/runs/${runId}` : `/api/projects/${projectId}`;
    const fail = (status: number | null) => live && setState({ kind: 'error', path, status });
    setState({ kind: 'loading' });
    async function read(): Promise<void> {
      try {
        if (runId) {
          const { data, error, response } = await api.GET('/runs/{run_id}', {
            params: { path: { run_id: runId } },
          });
          if (error || !data) return void fail(response.status);
          if (live) setState({ kind: 'run', run: data });
        } else if (projectId) {
          const { data, error, response } = await api.GET('/projects/{project_id}', {
            params: { path: { project_id: projectId } },
          });
          if (error || !data) return void fail(response.status);
          if (live) setState({ kind: 'project', project: data });
        } else if (live) {
          setState({ kind: 'project', project: null });
        }
      } catch {
        fail(null);
      }
    }
    void read();
    return () => {
      live = false;
    };
  }, [runId, projectId, attempt]);

  if (state.kind === 'error') {
    return (
      <FailedFetch
        method="GET"
        path={state.path}
        status={state.status}
        onRetry={() => setAttempt((n) => n + 1)}
        testId="ini-summary-failed"
        retryTestId="ini-summary-retry"
      />
    );
  }
  if (state.kind === 'loading') return null;

  if (state.kind === 'project') {
    return (
      <section className="ini-summary" data-testid="ini-summary">
        {notStartedLines(workflow, previous, state.project).map((line) => (
          <p key={line}>{line}</p>
        ))}
      </section>
    );
  }

  const { run } = state;
  return (
    <section className="ini-summary" data-testid="ini-summary">
      <p className="ini-section-head">
        WORKFLOW {workflow.position} · {workflow.workflow.toUpperCase()} · AUTO ·{' '}
        {workflow.template}@{workflow.version}
      </p>
      {workflow.token ? (
        <span className="ini-card-token" data-signal={tokenSignal(workflow.token)}>
          <span className="ini-card-chip" />
          {workflow.token}
        </span>
      ) : null}
      <p>{workflow.line}</p>
      <p>{run.budget_usd ? `$${run.spend_usd} / $${run.budget_usd}` : `$${run.spend_usd}`}</p>
      <p>
        {run.branch} · {run.repository}
      </p>
      <p>
        <a data-testid="ini-open-workflow" href={`/workflows/${run.id}`}>
          Open workflow
        </a>
      </p>
      <p className="ini-summary-note">{FIXED_LINE}</p>
    </section>
  );
}
