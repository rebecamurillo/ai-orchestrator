/**
 * Every string the Run page's metric glance prints (EXPERIENCE §4) is built here; components
 * only place them. Catalogue text (labels, methods, reasons) is never authored here (RM-2).
 */
import type { components } from '../../api/schema';
import { countSpans, formatValue } from '../metrics/format';
import type { OriginTarget } from '../../stores/metric-ui';

type MetricValueOut = components['schemas']['MetricValueOut'];
type ResultVersionOut = components['schemas']['ResultVersionOut'];
type CalculationOut = components['schemas']['CalculationOut'];

export const FIGURES_DIFFER = 'FIGURES DIFFER';
export const RECALCULATE_LABEL = 'RECALCULATE METRICS';
export const NO_VERSION = 'no result version';
export const RUNNING_WORD = 'running';
const GATE_LINE = 'the budget gate uses the higher figure';

export function runValue(
  items: readonly MetricValueOut[],
  metricId: string,
  source?: string,
): MetricValueOut | null {
  return (
    items.find(
      (v) =>
        v.scope_type === 'run' &&
        v.metric_id === metricId &&
        (source === undefined || v.source === source),
    ) ?? null
  );
}

export function isEnded(status: string): boolean {
  return status === 'done' || status === 'failed' || status === 'cancelled';
}

const cents = (v: MetricValueOut): number => Math.round(Number(v.value_num) * 100);

export function figuresDiffer(
  gateway: MetricValueOut | null,
  harness: MetricValueOut | null,
): { line: string; gate: string } | null {
  if (!gateway || !harness || gateway.value_num === null || harness.value_num === null) {
    return null;
  }
  const g = cents(gateway);
  const h = cents(harness);
  if (g === h) return null;
  const higher = h > g ? 'harness' : 'gateway';
  const lower = Math.min(g, h);
  const gap = Math.abs(g - h);
  const pct = lower > 0 ? ` (${((gap / lower) * 100).toFixed(1)} %)` : '';
  const usd = (n: number) => formatValue(String(n / 100), 'USD');
  return {
    line: `gateway ${usd(g)} · harness ${usd(h)} · ${higher} is ${usd(gap)} higher${pct}`,
    gate: GATE_LINE,
  };
}

/** The summed retry count, the first missing word when any count is missing, or null. */
export function retriesCount(items: readonly MetricValueOut[]): string | null {
  const rows = items.filter((v) => v.scope_type === 'run' && v.metric_id === 'process.retries');
  if (rows.length === 0) return null;
  const missing = rows.find((v) => v.value_num === null);
  if (missing) return missing.missing ?? '';
  return String(rows.reduce((sum, v) => sum + Number(v.value_num), 0));
}

const latestOf = (versions: readonly ResultVersionOut[]): number =>
  Math.max(0, ...versions.map((v) => v.n));

export function versionLine(
  versions: readonly ResultVersionOut[],
  selected: number,
): string | null {
  const latest = latestOf(versions);
  if (versions.length === 0 || selected >= latest) return null;
  return `showing v${selected} of ${versions.length} · latest is v${latest}`;
}

export function nextVersion(versions: readonly ResultVersionOut[]): number {
  return latestOf(versions) + 1;
}

export function recalcConfirmLine(versions: readonly ResultVersionOut[]): string {
  const head = `Creates v${nextVersion(versions)} of this Run's metrics: part A from the Run record.`;
  if (versions.length === 0) return head;
  const latest = latestOf(versions);
  return latest === 1 ? `${head} v1 is kept.` : `${head} v1 to v${latest} are kept.`;
}

export function calcLine(calc: CalculationOut | null): string | null {
  if (!calc) return null;
  if (calc.state === 'failed') return `calculation v${calc.target_n} failed · no version created ·`;
  if (calc.state === 'done') return null;
  const at = (calc.started_at ?? calc.queued_at).slice(11, 19);
  return `calculating v${calc.target_n} · started ${at}`;
}

export interface TargetContext {
  runLabel: string;
  versions: readonly ResultVersionOut[];
  selected: number | null;
  latest: number | null;
  /** Absent where the page does not know it: the drawer then reads it from the origin. */
  projectName?: string;
  items: readonly MetricValueOut[];
  subscription: boolean;
}

export function targetFor(value: MetricValueOut, ctx: TargetContext): OriginTarget {
  const shown = ctx.selected ?? ctx.latest;
  return {
    value,
    runLabel: ctx.runLabel,
    version: ctx.versions.find((v) => v.n === shown) ?? null,
    latest: ctx.latest,
    projectName: ctx.projectName,
    spans: countSpans(ctx.items),
    subscription: ctx.subscription,
  };
}
