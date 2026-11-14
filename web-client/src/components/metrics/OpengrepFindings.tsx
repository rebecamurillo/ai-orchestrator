import { useEffect, useState } from 'react';

import { api } from '../../api/client';
import type { components } from '../../api/schema';
import { findingText, findingsPath, newFindings } from '../../lib/metrics/findings';
import { sarifHref } from '../../lib/metrics/sarif';
import '../../styles/metrics.css';

type FindingOut = components['schemas']['FindingOut'];

interface Source {
  runId: string;
  analysisId: string;
  tool: string;
  repository: string;
  kind?: 'security' | 'bug';
}

type State =
  { kind: 'loading' } | { kind: 'ready'; found: FindingOut[] } | { kind: 'failed'; line: string };

/** The new findings of one kind that opengrep stored for an analysis, and its SARIF download. */
export default function OpengrepFindings({
  source,
}: {
  source: Source & { kind: 'security' | 'bug' };
}) {
  const [state, setState] = useState<State>({ kind: 'loading' });
  const path = findingsPath(source.runId, source.analysisId);

  useEffect(() => {
    let live = true;
    setState({ kind: 'loading' });
    api
      .GET('/runs/{run_id}/analysis/{analysis_id}/findings', {
        params: { path: { run_id: source.runId, analysis_id: source.analysisId } },
      })
      .then(({ data, response }) => {
        if (!live) return;
        setState(
          data !== undefined
            ? { kind: 'ready', found: newFindings(data.items, source.kind) }
            : { kind: 'failed', line: `GET ${path} · ${response.status}` },
        );
      })
      .catch(() => live && setState({ kind: 'failed', line: `GET ${path} · network error` }));
    return () => {
      live = false;
    };
  }, [source.runId, source.analysisId, source.kind, path]);

  return (
    <div className="findings-list" data-testid={`findings-${source.tool}`}>
      {state.kind === 'ready' &&
        (state.found.length === 0 ? (
          <p>no new findings in this report</p>
        ) : (
          <ul>
            {state.found.map((f, at) => (
              <li key={at}>{findingText(f)}</li>
            ))}
          </ul>
        ))}
      {state.kind === 'failed' && <p>{state.line}</p>}
      <a href={sarifHref(source.runId, source.analysisId, source.tool)} download>
        {`SARIF · ${source.tool} · ${source.repository}`}
      </a>
    </div>
  );
}
