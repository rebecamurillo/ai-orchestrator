import { useEffect, useState } from 'react';

import { api } from '../../api/client';
import { findingLine, sarifFindings, sarifHref, type SarifFinding } from '../../lib/metrics/sarif';
import '../../styles/metrics.css';
import OpengrepFindings from './OpengrepFindings';

interface Source {
  runId: string;
  analysisId: string;
  tool: string;
  repository: string;
  kind?: 'security' | 'bug';
}

type State =
  { kind: 'loading' } | { kind: 'ready'; found: SarifFinding[] } | { kind: 'failed'; line: string };

/** One stored SARIF report: its findings, one line each, and the download. */
export default function FindingsList({ source }: { source: Source }) {
  if (source.tool === 'opengrep' && source.kind !== undefined) {
    return <OpengrepFindings source={{ ...source, kind: source.kind }} />;
  }
  return <SarifFindings source={source} />;
}

function SarifFindings({ source }: { source: Source }) {
  const [state, setState] = useState<State>({ kind: 'loading' });
  const href = sarifHref(source.runId, source.analysisId, source.tool);

  useEffect(() => {
    let live = true;
    api
      .GET('/runs/{run_id}/analysis/{analysis_id}/sarif/{tool}', {
        params: {
          path: { run_id: source.runId, analysis_id: source.analysisId, tool: source.tool },
        },
        parseAs: 'json',
      })
      .then(({ data, response }) => {
        if (!live) return;
        setState(
          data !== undefined
            ? { kind: 'ready', found: sarifFindings(data) }
            : { kind: 'failed', line: `GET ${href} · ${response.status}` },
        );
      })
      .catch(() => live && setState({ kind: 'failed', line: `GET ${href} · network error` }));
    return () => {
      live = false;
    };
  }, [source.runId, source.analysisId, source.tool, href]);

  return (
    <div className="findings-list" data-testid={`findings-${source.tool}`}>
      {state.kind === 'ready' &&
        (state.found.length === 0 ? (
          <p>no findings in this report</p>
        ) : (
          <ul>
            {state.found.map((f, at) => (
              <li key={at} title={f.message}>
                {findingLine(f)}
              </li>
            ))}
          </ul>
        ))}
      {state.kind === 'failed' && <p>{state.line}</p>}
      <a href={href} download>
        {`SARIF · ${source.tool} · ${source.repository}`}
      </a>
    </div>
  );
}
