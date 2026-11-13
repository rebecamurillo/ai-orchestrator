/**
 * STATIC SIGNALS ON THE CHANGE (epic 5 story 5): the Run row then one row per repository, per
 * tier, with the tool footer always printed. Every figure is a stored value, printed as given.
 */
import { useStore } from '@nanostores/react';
import { useEffect } from 'react';

import type { components } from '../../api/schema';
import {
  FINDING_TOOLS,
  NA_WORD,
  RATE_HEAD,
  RAW_HEAD,
  STATIC_HEAD,
  STATIC_SUB,
  TIER_2,
  TIER_3,
  footerLines,
  notRunLine,
  sourceWord,
  splitCells,
  staticTable,
  type StaticCell,
  type StaticScope,
} from '../../lib/metrics/static-signals';
import { targetFor, type TargetContext } from '../../lib/run/metrics-glance';
import { $catalogue } from '../../stores/catalogue';
import { $runAnalysis, loadRunAnalysis } from '../../stores/run-analysis';
import type { OriginTarget } from '../../stores/metric-ui';
import FailedFetch from '../FailedFetch';
import HintControl from '../metrics/HintControl';
import MissingWord from '../metrics/MissingWord';
import ValueCell from '../metrics/ValueCell';

type MetricValueOut = components['schemas']['MetricValueOut'];
type AnalysisOut = components['schemas']['AnalysisOut'];

interface Props {
  runId: string;
  shown: number;
  items: readonly MetricValueOut[];
  ctx: TargetContext;
  set: 'headline' | 'all';
}

function targetOf(
  cell: StaticCell,
  metricId: string,
  scope: StaticScope,
  analyses: readonly AnalysisOut[],
  runId: string,
  ctx: TargetContext,
): OriginTarget {
  const target = targetFor(cell as MetricValueOut, ctx);
  const tool = FINDING_TOOLS[metricId];
  if (tool === undefined) return target;
  const sources = (scope.analysis ? [scope.analysis] : analyses).filter((a) =>
    a.sarif_tools.includes(tool),
  );
  return {
    ...target,
    findings: sources.map((a) => ({
      runId,
      analysisId: a.analysis_id,
      tool,
      repository: a.repository_path,
    })),
  };
}

export default function StaticSignals({ runId, shown, items, ctx, set }: Props) {
  const state = useStore($runAnalysis);
  const { entries } = useStore($catalogue);

  useEffect(() => {
    void loadRunAnalysis(runId, shown);
  }, [runId, shown]);

  const current = state.runId === runId && state.version === shown;
  const analyses = current ? state.items : [];
  const hasCode = items.some((v) => v.metric_id.startsWith('code.'));

  let body;
  if (!current || state.status === 'idle' || state.status === 'loading') {
    body = <p className="wf-metrics-note">…</p>;
  } else if (state.status === 'failed' && state.failed) {
    body = (
      <FailedFetch
        method="GET"
        path={state.failed.path}
        status={state.failed.status}
        onRetry={() => void loadRunAnalysis(runId, shown)}
      />
    );
  } else if (analyses.length === 0 && !hasCode) {
    body = <p className="wf-metrics-note">{notRunLine(shown)}</p>;
  } else {
    const tiers = staticTable(items, analyses, entries, set);
    body = (
      <>
        <table className="wf-metrics-static" data-testid="static-signals-table">
          <thead>
            <tr>
              <th scope="col">signal</th>
              <th scope="col">{RAW_HEAD}</th>
              <th scope="col">{RATE_HEAD}</th>
            </tr>
          </thead>
          <tbody>
            {tiers.map((tier) => (
              <TierRows
                key={tier.tier}
                head={tier.head}
                scopes={tier.scopes}
                analyses={analyses}
                runId={runId}
                ctx={ctx}
              />
            ))}
            {[TIER_2, TIER_3].map((head) => (
              <NotAvailable key={head} head={head} />
            ))}
          </tbody>
        </table>
        {analyses.length > 0 && (
          <div className="static-foot" data-testid="static-foot">
            {footerLines(analyses).map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        )}
      </>
    );
  }

  return (
    <section className="wf-metrics-static-block" data-testid="static-signals">
      <h3 className="wf-metrics-section">{STATIC_HEAD}</h3>
      <p className="wf-metrics-note">{STATIC_SUB}</p>
      {body}
    </section>
  );
}

function NotAvailable({ head }: { head: string }) {
  return (
    <>
      <tr className="tier">
        <th colSpan={3} scope="colgroup">
          {head}
        </th>
      </tr>
      <tr>
        <td colSpan={3}>
          <MissingWord word={NA_WORD} />
        </td>
      </tr>
    </>
  );
}

function TierRows({
  head,
  scopes,
  analyses,
  runId,
  ctx,
}: {
  head: string;
  scopes: StaticScope[];
  analyses: readonly AnalysisOut[];
  runId: string;
  ctx: TargetContext;
}) {
  return (
    <>
      <tr className="tier">
        <th colSpan={3} scope="colgroup">
          {head}
        </th>
      </tr>
      {scopes.map((scope) => (
        <ScopeRows key={scope.key} scope={scope} analyses={analyses} runId={runId} ctx={ctx} />
      ))}
    </>
  );
}

function ScopeRows({
  scope,
  analyses,
  runId,
  ctx,
}: {
  scope: StaticScope;
  analyses: readonly AnalysisOut[];
  runId: string;
  ctx: TargetContext;
}) {
  return (
    <>
      <tr data-testid={`static-scope-${scope.key}`}>
        <th colSpan={3} scope="rowgroup">
          {scope.name}
          {scope.detail !== null && <div className="static-detail">{scope.detail}</div>}
        </th>
      </tr>
      {scope.rows.map((row) => {
        const { raws, rates, small } = splitCells(row.cells);
        const label = (cell: StaticCell) => (raws.length > 1 ? sourceWord(cell.source) : null);
        const place = (cell: StaticCell, at: number) => (
          <span key={at} className="static-cell">
            {label(cell) !== null && <span className="metric-label">{label(cell)} </span>}
            <ValueCell target={targetOf(cell, row.metricId, scope, analyses, runId, ctx)} />
          </span>
        );
        return (
          <tr key={row.metricId} data-testid={`static-row-${scope.key}-${row.metricId}`}>
            <td>
              <HintControl metricId={row.metricId} showLabel />
            </td>
            <td>
              {row.cells.length === 0 ? '—' : raws.map(place)}
              {small.map(place)}
            </td>
            <td>{rates.map(place)}</td>
          </tr>
        );
      })}
    </>
  );
}
