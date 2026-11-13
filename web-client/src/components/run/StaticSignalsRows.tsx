/** The rows of the STATIC SIGNALS table: a tier head, a scope row, then one row per metric. */
import type { components } from '../../api/schema';
import { partialWord } from '../../lib/metrics/format';
import {
  FINDING_IDS,
  FINDING_TOOLS,
  NA_WORD,
  cellWords,
  splitCells,
  type StaticCell,
  type StaticScope,
} from '../../lib/metrics/static-signals';
import { targetFor, type TargetContext } from '../../lib/run/metrics-glance';
import type { OriginTarget } from '../../stores/metric-ui';
import HintControl from '../metrics/HintControl';
import MissingWord from '../metrics/MissingWord';
import ValueCell from '../metrics/ValueCell';

type MetricValueOut = components['schemas']['MetricValueOut'];
type AnalysisOut = components['schemas']['AnalysisOut'];

export function targetOf(
  cell: StaticCell,
  metricId: string,
  scope: StaticScope | null,
  analyses: readonly AnalysisOut[],
  runId: string,
  ctx: TargetContext,
): OriginTarget {
  const target = targetFor(cell as MetricValueOut, ctx);
  const tool = FINDING_TOOLS[metricId];
  if (tool === undefined) return target;
  const kind = FINDING_IDS[metricId];
  const sources = (scope?.analysis ? [scope.analysis] : analyses).filter((a) =>
    a.sarif_tools.includes(tool),
  );
  return {
    ...target,
    findings: sources.map((a) => ({
      runId,
      analysisId: a.analysis_id,
      tool,
      repository: a.repository_path,
      ...(kind === undefined ? {} : { kind }),
    })),
  };
}

export function NotAvailable({ head }: { head: string }) {
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

interface TierProps {
  analyses: readonly AnalysisOut[];
  runId: string;
  ctx: TargetContext;
}

export function TierRows({
  head,
  scopes,
  ...rest
}: TierProps & { head: string; scopes: StaticScope[] }) {
  return (
    <>
      <tr className="tier">
        <th colSpan={3} scope="colgroup">
          {head}
        </th>
      </tr>
      {scopes.map((scope) => (
        <ScopeRows key={scope.key} scope={scope} {...rest} />
      ))}
    </>
  );
}

function ScopeRows({ scope, analyses, runId, ctx }: TierProps & { scope: StaticScope }) {
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
        const place = (cell: StaticCell, at: number) => {
          const words = cellWords(row.metricId, cell.source);
          const partial = partialWord(cell as MetricValueOut);
          return (
            <span key={at} className="static-cell">
              {raws.length > 1 && words.before !== null && (
                <span className="metric-label">{words.before} </span>
              )}
              <ValueCell target={targetOf(cell, row.metricId, scope, analyses, runId, ctx)} />
              {words.after !== null && <span className="metric-label"> {words.after}</span>}
              {partial !== null && <span className="static-partial"> {partial}</span>}
            </span>
          );
        };
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
