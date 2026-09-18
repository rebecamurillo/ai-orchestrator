/**
 * Step-run detail island (story 1-2): full history for one step.
 *
 * Receives `runId` and `dotPath` (dot-index encoded) from the Astro page.  Decodes
 * `dotPath` to bracket form, fetches `GET /runs/{runId}/steps/{bracketPath}`, and
 * polls while any attempt is running.
 *
 * Renders:
 * - Header: breadcrumb (→ run), label, bracket path, status chip, kind, gate
 * - `with_resolved` key-value block
 * - Attempts list, newest first, latest pre-selected
 * - Selected attempt: dispatch prompt, retry prompt, result or command+exit line
 * - `LogViewer` for the selected attempt's log
 * - Blocked/checkpointed: reason + "answer on the run" link; no signal actions
 */
import { useEffect, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import { api } from '../api/client';
import { $poll, configurePolling, stopPolling } from '../stores/poll';
import LogViewer from '../components/run/LogViewer';
import { decode } from '../lib/step-path';

interface AttemptDetail {
  id: string;
  n: number;
  status: string;
  token: string;
  started_at: string | null;
  ended_at: string | null;
  seconds: number | null;
  harness: string | null;
  model: string | null;
  session_id: string | null;
  exit_code: number | null;
  cost_usd: string | null;
  cost_provisional: boolean;
  tokens_in: number | null;
  tokens_out: number | null;
  dispatch_prompt: string | null;
  retry_prompt: string | null;
  result: string | null;
  command: string | null;
}

interface StepDetail {
  seq: number;
  path: string;
  label: string;
  kind: string;
  gate: string;
  status: string;
  token: string;
  reason: string | null;
  with_resolved: Record<string, unknown>;
  attempts: AttemptDetail[];
}

interface Props {
  runId: string;
  /** The step path in dot-index encoding, from the Astro catch-all param. */
  dotPath: string;
}

type Phase = { kind: 'loading' } | { kind: 'ready' } | { kind: 'error'; status: number | null };

const STOPPED_STATUSES = new Set(['blocked', 'checkpoint']);

export default function StepDetail({ runId, dotPath }: Props) {
  const bracketPath = decode(dotPath);
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [detail, setDetail] = useState<StepDetail | null>(null);
  const [selectedN, setSelectedN] = useState<number | null>(null);
  const pollTick = useStore($poll);
  const requestSeqRef = useRef(0);
  const mountedTickRef = useRef(pollTick);

  async function fetchDetail(): Promise<void> {
    const seq = ++requestSeqRef.current;
    try {
      const encoded = encodeURIComponent(bracketPath);
      const { data, response } = await api.GET('/runs/{run_id}/steps/{step_path}', {
        params: { path: { run_id: runId, step_path: encoded } },
      });
      if (seq !== requestSeqRef.current) return;
      if (!response.ok) {
        setPhase({ kind: 'error', status: response.status });
        stopPolling();
        return;
      }
      if (!data) {
        setPhase({ kind: 'error', status: response.status });
        stopPolling();
        return;
      }
      setDetail(data);
      setPhase({ kind: 'ready' });
      // Select the latest attempt (first in newest-first list) when first loaded
      if (data.attempts.length > 0 && selectedN === null) {
        setSelectedN(data.attempts[0].n);
      }
      const hasRunning = data.attempts.some((a) => a.status === 'running');
      configurePolling(hasRunning);
    } catch {
      if (seq !== requestSeqRef.current) return;
      stopPolling();
      setPhase({ kind: 'error', status: null });
    }
  }

  useEffect(() => {
    void fetchDetail();
    return () => stopPolling();
  }, [runId, dotPath]);

  useEffect(() => {
    if (pollTick === mountedTickRef.current) return;
    void fetchDetail();
  }, [pollTick]);

  if (phase.kind === 'loading') return null;

  if (phase.kind === 'error') {
    return (
      <div data-testid="step-detail-error">
        <p>failed to load step detail ({phase.status ?? 'network error'})</p>
        <button type="button" onClick={() => void fetchDetail()}>
          retry
        </button>
      </div>
    );
  }

  if (!detail) return null;

  const selectedAttempt = detail.attempts.find((a) => a.n === selectedN) ?? detail.attempts[0];
  const isStopped = STOPPED_STATUSES.has(detail.status);

  return (
    <div data-testid="step-detail">
      {/* ── Header ── */}
      <div className="wf-step-detail-header">
        <nav className="wf-step-detail-crumb">
          <a href={`/workflows/${runId}`}>run</a>
          {' › '}
          <span>{detail.label}</span>
        </nav>
        <div className="wf-step-detail-meta">
          <code className="wf-step-detail-path">{detail.path}</code>
          <span className="wf-step-token" data-testid="step-detail-token">
            {detail.token}
          </span>
          <span className="wf-step-detail-kind">{detail.kind}</span>
          <span className="wf-step-detail-gate">{detail.gate}</span>
        </div>
      </div>

      {/* ── Blocked / checkpointed ── */}
      {isStopped && detail.reason && (
        <div className="wf-step-detail-stopped" data-testid="step-detail-stopped">
          <p>{detail.reason}</p>
          <a href={`/workflows/${runId}`}>answer on the run</a>
        </div>
      )}

      {/* ── with_resolved context ── */}
      {Object.keys(detail.with_resolved).length > 0 && (
        <details className="wf-step-detail-context">
          <summary>dispatch context</summary>
          <dl className="wf-kv">
            {Object.entries(detail.with_resolved).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>
                  <code>{typeof value === 'string' ? value : JSON.stringify(value)}</code>
                </dd>
              </div>
            ))}
          </dl>
        </details>
      )}

      {/* ── Attempts ── */}
      {detail.attempts.length === 0 ? (
        <p className="wf-step-detail-no-attempts" data-testid="step-detail-no-attempts">
          {detail.status === 'skipped' ? null : 'no attempts yet'}
        </p>
      ) : (
        <div className="wf-step-detail-attempts">
          <h3>attempts</h3>
          <ul className="wf-step-detail-attempt-list">
            {detail.attempts.map((attempt) => (
              <li key={attempt.n}>
                <button
                  type="button"
                  data-selected={attempt.n === selectedN}
                  onClick={() => setSelectedN(attempt.n)}
                >
                  attempt {attempt.n} · {attempt.token}
                  {attempt.harness && ` · ${attempt.harness}`}
                  {attempt.seconds != null && ` · ${Math.round(attempt.seconds)}s`}
                </button>
              </li>
            ))}
          </ul>

          {selectedAttempt && (
            <div className="wf-step-detail-attempt" data-testid="step-detail-attempt">
              {/* Session id */}
              {selectedAttempt.session_id && (
                <div className="wf-step-detail-session">
                  <span className="wf-step-detail-session-label">session</span>
                  <code className="wf-step-detail-session-id" data-testid="step-detail-session-id">
                    {selectedAttempt.session_id}
                  </code>
                  <button
                    type="button"
                    className="wf-step-detail-copy"
                    onClick={() => void navigator.clipboard.writeText(selectedAttempt.session_id!)}
                    title="copy session id"
                  >
                    copy
                  </button>
                </div>
              )}

              {/* Dispatch prompt */}
              {selectedAttempt.dispatch_prompt && (
                <details className="wf-step-detail-prompt">
                  <summary>dispatch prompt</summary>
                  <pre className="wf-step-detail-prompt-text">
                    {selectedAttempt.dispatch_prompt}
                  </pre>
                </details>
              )}

              {/* Retry prompt */}
              {selectedAttempt.retry_prompt && (
                <details className="wf-step-detail-retry-prompt">
                  <summary>retry prompt</summary>
                  <pre className="wf-step-detail-retry-prompt-text">
                    {selectedAttempt.retry_prompt}
                  </pre>
                </details>
              )}

              {/* Shell command + exit code */}
              {selectedAttempt.command != null && (
                <div className="wf-step-detail-command" data-testid="step-detail-command">
                  <code>{selectedAttempt.command}</code>
                  {selectedAttempt.exit_code != null && (
                    <span className="wf-step-detail-exit"> exit {selectedAttempt.exit_code}</span>
                  )}
                </div>
              )}

              {/* Result */}
              {selectedAttempt.result && (
                <details className="wf-step-detail-result" open>
                  <summary>auto run result</summary>
                  <pre className="wf-step-detail-result-text">{selectedAttempt.result}</pre>
                </details>
              )}

              {/* Running indicator when no result yet */}
              {selectedAttempt.status === 'running' && !selectedAttempt.result && (
                <p className="wf-step-detail-running">— running</p>
              )}

              {/* Log viewer */}
              <div className="wf-step-detail-log">
                <h4>log</h4>
                <LogViewer
                  runId={runId}
                  attemptId={selectedAttempt.id}
                  isRunning={selectedAttempt.status === 'running'}
                  logPath={null}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
