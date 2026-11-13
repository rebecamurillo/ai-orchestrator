/**
 * Attempts table (story 5, 2026-09-25): stateless component that renders an HTML table of
 * attempt rows for the step-run detail page.
 *
 * `AttemptDetail` is exported here (moves from `StepDetail.tsx`) so the island can import the
 * type back without duplication. `AttemptsTable` is the default export.
 *
 * Columns: #, status, harness, model, duration, cost, then the gateway / harness figures and
 * the four token classes of the Run's metrics (only the catalogued ones, from `values`), exit,
 * actions. The `cost` head carries the `spend.recorded` hint; the figures open their origin drawer.
 * Status token is the only signal-coloured cell (NFR-6): the span uses `.wf-step-token` with
 * `data-signal={tokenSignal(attempt.token)}`; no other cell carries a signal hue.
 * `data-selected` on `<tr>` marks the selected row; `step-prompt-{n}` and `step-reach-{n}`
 * testids are preserved in the actions column.
 * Testable with renderToStaticMarkup.
 */
import { Fragment } from 'react';
import { useStore } from '@nanostores/react';

import type { components } from '../../api/schema';
import { tokenSignal } from '../../lib/board/format';
import { targetFor, type TargetContext } from '../../lib/run/metrics-glance';
import { ATTEMPT_COLUMNS } from '../../lib/run/metrics-tab';
import { $catalogue } from '../../stores/catalogue';
import HintControl from '../metrics/HintControl';
import ValueCell from '../metrics/ValueCell';
import type { DrawerContent } from './HelperDrawer';

export interface AttemptDetail {
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
  resume_command?: string | null;
  session_lifetime_ends_at?: string | null;
  /** Omitted by the API for an `agent` attempt (AD-21). */
  role?: 'agent' | 'consult' | 'session';
}

interface Props {
  attempts: readonly AttemptDetail[];
  selectedN: number | null;
  onSelect: (n: number) => void;
  onDrawer: (n: number, content: DrawerContent) => void;
  /** Attempt-scope metric values of this step; with `ctx`, adds the figure columns. */
  values?: readonly components['schemas']['MetricValueOut'][];
  ctx?: TargetContext;
}

const ROLE_SUFFIX: Record<string, string> = { consult: ' · senior', session: ' · session' };

function numberText(attempt: AttemptDetail): string {
  return `${attempt.n}${ROLE_SUFFIX[attempt.role ?? 'agent'] ?? ''}`;
}

function durationText(seconds: number | null): string {
  if (seconds === null) return '—';
  return `${Math.round(seconds)}s`;
}

function costText(cost_usd: string | null): string {
  if (cost_usd === null) return '—';
  return `$${cost_usd}`;
}

export default function AttemptsTable({
  attempts,
  selectedN,
  onSelect,
  onDrawer,
  values = [],
  ctx,
}: Props) {
  const { entries } = useStore($catalogue);
  const columns = ctx ? ATTEMPT_COLUMNS.filter((id) => entries[id]) : [];
  return (
    <div className="wf-step-attempts-scroll">
      <table className="wf-step-attempts">
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">status</th>
            <th scope="col">harness</th>
            <th scope="col">model</th>
            <th scope="col">duration</th>
            <th scope="col">
              cost
              <HintControl metricId="spend.recorded" />
            </th>
            {columns.map((id) => (
              <th key={id} scope="col">
                <HintControl metricId={id} showLabel />
              </th>
            ))}
            <th scope="col">exit</th>
            <th scope="col">actions</th>
          </tr>
        </thead>
        <tbody>
          {attempts.map((attempt) => (
            <tr
              key={attempt.id}
              data-selected={attempt.n === selectedN}
              onClick={() => onSelect(attempt.n)}
            >
              <td>{numberText(attempt)}</td>
              <td>
                <span className="wf-step-token" data-signal={tokenSignal(attempt.token)}>
                  {attempt.token}
                </span>
              </td>
              <td>{attempt.harness ?? '—'}</td>
              <td>{attempt.model ?? '—'}</td>
              <td>{durationText(attempt.seconds)}</td>
              <td>{costText(attempt.cost_usd)}</td>
              {columns.map((id) => (
                <td key={id} className="wf-step-figure">
                  {values
                    .filter((v) => v.metric_id === id && v.attempt_n === attempt.n)
                    .map((v, at) => (
                      <Fragment key={`${v.source ?? ''}-${at}`}>
                        {at > 0 ? ' · ' : null}
                        <ValueCell target={targetFor(v, ctx as TargetContext)} />
                      </Fragment>
                    ))}
                </td>
              ))}
              <td>{attempt.exit_code ?? '—'}</td>
              <td>
                {attempt.command === null && (
                  <>
                    <button
                      type="button"
                      data-testid={`step-prompt-${attempt.n}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onDrawer(attempt.n, 'prompt-result');
                      }}
                    >
                      prompt · result
                    </button>
                    {attempt.resume_command != null && (
                      <button
                        type="button"
                        data-testid={`step-reach-${attempt.n}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onDrawer(attempt.n, 'reach-agent');
                        }}
                      >
                        reach agent
                      </button>
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
