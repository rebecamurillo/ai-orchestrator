/**
 * The static-signal charts of the comparison: raw run-scope values drawn as bars, the stored
 * rate printed as the value label, `not run` for a Run with no analysis. Nothing is computed.
 */
import type { components } from '../../api/schema';
import { NO_CELL, NOT_RUN_WORD, runCells } from '../metrics/compare';
import { formatValue } from '../metrics/format';
import { splitCells, toolFlag, toolLine } from '../metrics/static-signals';
import type { CompareMark, CompareRow } from './compare-charts';

type CompareOut = components['schemas']['CompareOut'];
type CompareCellOut = components['schemas']['CompareCellOut'];
type CompareMetricOut = components['schemas']['CompareMetricOut'];
type MetricValueOut = components['schemas']['MetricValueOut'];

export interface StaticSpec {
  ids: string[];
  source?: string;
  rate?: string;
}

export const isStaticSpec = (spec: { ids: string[] }): boolean => spec.ids[0].startsWith('code.');

const asValue = (cell: CompareCellOut, metricId: string): MetricValueOut => ({
  ...cell,
  metric_id: metricId,
  origin: null,
});

function rateLabel(cell: CompareCellOut | undefined): string | undefined {
  if (cell === undefined) return undefined;
  return cell.value_num === null
    ? (cell.missing ?? undefined)
    : `${formatValue(cell.value_num, 'ratio')} per 100`;
}

export function staticMark(
  payload: CompareOut,
  metric: CompareMetricOut,
  spec: StaticSpec,
  runId: string,
): CompareMark {
  const cells = runCells(metric, runId);
  const raw = spec.source ? cells.find((c) => c.source === spec.source) : splitCells(cells).raws[0];
  if (raw === undefined) {
    const word = payload.diff_size[runId] === NOT_RUN_WORD ? NOT_RUN_WORD : NO_CELL;
    return { value: null, word };
  }
  if (raw.value_num === null) return { value: null, word: raw.missing ?? NO_CELL };
  const rate = rateLabel(cells.find((c) => c.source === (spec.rate ?? 'per_100')));
  return { value: asValue(raw, metric.metric_id), ...(rate === undefined ? {} : { rate }) };
}

/** Dots a Run whose tool versions differ from Run 1's; returns the chart's flag. */
export function markToolVersions(
  payload: CompareOut,
  metric: CompareMetricOut,
  rows: CompareRow[],
): string | null {
  const flag = toolFlag(metric, payload.runs);
  if (flag === null) return null;
  const first = toolLine(metric, payload.runs[0].run_id);
  rows.forEach((row, at) => {
    const line = toolLine(metric, payload.runs[at].run_id);
    if (at > 0 && line !== null && line !== first) row.marks[0].dotted = line;
  });
  return flag;
}
