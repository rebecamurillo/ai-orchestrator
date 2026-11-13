/**
 * The Run page chart models. Rows come from the table's own row functions (`scopeTree`,
 * `flatRows`, `valuesAt`) and carry the API's values untouched: no figure is computed here (RM-7).
 * Labels come from the catalogue (RM-2); the only authored strings are the titles below and
 * `NO_MODEL_GATEWAY`.
 */
import type { components } from '../../api/schema';
import { flatRows, scopeTree, valuesAt, type ScopeNode } from '../run/metrics-tab';
import type { MetricsSet } from '../run/metrics-tab';

type MetricValueOut = components['schemas']['MetricValueOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];
type Entries = Record<string, CatalogueEntryOut>;

export const CHART_TITLES = {
  scope: 'where the money went, by scope',
  role: 'cost by role',
  model: 'cost by model',
  time: 'where the time went',
} as const;
export const tokensTitle = (label: string): string => `tokens by role · ${label}`;
export const NO_MODEL_GATEWAY = 'not available (per-model gateway split not stored)';
export const HEADLINE_TOKENS = ['tokens.output', 'tokens.cache_read'] as const;
export const ALL_TOKENS = [...HEADLINE_TOKENS, 'tokens.cache_write', 'tokens.input'] as const;

export interface ChartRow {
  id: string;
  label: string;
  value: MetricValueOut | null;
  texture?: 'hatch';
}

export interface PairRow {
  id: string;
  label: string;
  gateway: MetricValueOut | null;
  harness: MetricValueOut | null;
  gatewayWord?: string;
  gatewayShare?: MetricValueOut | null;
  harnessShare?: MetricValueOut | null;
}

export type RunChart =
  | { kind: 'pair'; title: string; metricIds: string[]; unit: string; rows: PairRow[] }
  | { kind: 'bar'; title: string; metricIds: string[]; unit: string; rows: ChartRow[] }
  | { kind: 'time'; title: string; metricIds: string[]; unit: string; rows: ChartRow[] };

const first = (
  items: readonly MetricValueOut[],
  id: string,
  type: string,
  key: string,
): MetricValueOut | null => valuesAt(items, id, type, key)[0] ?? null;

function shareAt(
  items: readonly MetricValueOut[],
  type: string,
  key: string,
  source: string,
): MetricValueOut | null {
  return valuesAt(items, 'cost.retries', type, key).find((v) => v.source === source) ?? null;
}

export function scopeRows(
  items: readonly MetricValueOut[],
  stepOrder: readonly string[],
): PairRow[] {
  const rows: PairRow[] = [];
  function walk(node: ScopeNode, parent: string): void {
    const keep = node.type === 'story' || (node.type === 'step' && parent !== 'story');
    if (keep) {
      rows.push({
        id: node.id,
        label: node.label,
        gateway: first(items, 'cost.gateway', node.type, node.key),
        harness: first(items, 'cost.harness', node.type, node.key),
        gatewayShare: shareAt(items, node.type, node.key, 'gateway'),
        harnessShare: shareAt(items, node.type, node.key, 'harness'),
      });
    }
    for (const child of node.children) walk(child, node.type);
  }
  walk(scopeTree(items, stepOrder), '');
  return rows;
}

export function roleOrder(
  items: readonly MetricValueOut[],
  stepOrder: readonly string[],
): string[] {
  const keys = flatRows(items, 'role');
  const rank = new Map<string, [number, number]>();
  for (const v of items) {
    if (v.scope_type !== 'attempt' || v.role === null) continue;
    const found = stepOrder.indexOf(v.scope_key.split('#')[0]);
    const mine: [number, number] = [
      found === -1 ? Number.MAX_SAFE_INTEGER : found,
      v.attempt_n ?? 0,
    ];
    const held = rank.get(v.role);
    if (!held || mine[0] < held[0] || (mine[0] === held[0] && mine[1] < held[1])) {
      rank.set(v.role, mine);
    }
  }
  const ranked = keys.filter((k) => rank.has(k));
  ranked.sort((a, b) => {
    const x = rank.get(a) as [number, number];
    const y = rank.get(b) as [number, number];
    return x[0] - y[0] || x[1] - y[1];
  });
  return [...ranked, ...keys.filter((k) => !rank.has(k))];
}

export function roleRows(
  items: readonly MetricValueOut[],
  stepOrder: readonly string[],
): PairRow[] {
  return roleOrder(items, stepOrder).map((key) => ({
    id: `role:${key}`,
    label: key,
    gateway: first(items, 'cost.gateway', 'role', key),
    harness: first(items, 'cost.harness', 'role', key),
  }));
}

export function tokenRows(
  items: readonly MetricValueOut[],
  stepOrder: readonly string[],
  metricId: string,
): ChartRow[] {
  return roleOrder(items, stepOrder).map((key) => ({
    id: `role:${key}`,
    label: key,
    value: first(items, metricId, 'role', key),
  }));
}

export function modelRows(items: readonly MetricValueOut[]): PairRow[] {
  const split = items.some((v) => v.metric_id === 'cost.gateway' && v.scope_type === 'model');
  return flatRows(items, 'model').map((key) => ({
    id: `model:${key}`,
    label: key,
    gateway: split ? first(items, 'cost.gateway', 'model', key) : null,
    harness: first(items, 'cost.harness', 'model', key),
    ...(split ? {} : { gatewayWord: NO_MODEL_GATEWAY }),
  }));
}

export function timeRows(items: readonly MetricValueOut[], entries: Entries): ChartRow[] {
  const rows: ChartRow[] = [];
  for (const id of ['time.machine', 'time.parked']) {
    const value = items.find((v) => v.metric_id === id && v.scope_type === 'run');
    if (value === undefined) continue;
    rows.push({
      id,
      label: entries[id]?.label ?? id,
      value,
      ...(id === 'time.parked' ? { texture: 'hatch' as const } : {}),
    });
  }
  return rows;
}

export function runCharts(
  entries: Entries,
  items: readonly MetricValueOut[],
  stepOrder: readonly string[],
  set: MetricsSet,
): RunChart[] {
  const charts: RunChart[] = [];
  const cost = ['cost.gateway', 'cost.harness'];
  const hasCost = cost.every((id) => entries[id]);
  const pair = (title: string, rows: PairRow[]): void => {
    if (hasCost && rows.length > 0) {
      charts.push({ kind: 'pair', title, metricIds: cost, unit: 'USD', rows });
    }
  };
  pair(CHART_TITLES.scope, scopeRows(items, stepOrder));
  pair(CHART_TITLES.role, roleRows(items, stepOrder));
  for (const id of set === 'all' ? ALL_TOKENS : HEADLINE_TOKENS) {
    const entry = entries[id];
    const rows = tokenRows(items, stepOrder, id);
    if (entry && rows.length > 0) {
      charts.push({
        kind: 'bar',
        title: tokensTitle(entry.label),
        metricIds: [id],
        unit: entry.unit,
        rows,
      });
    }
  }
  pair(CHART_TITLES.model, modelRows(items));
  const time = timeRows(items, entries);
  if (entries['time.machine'] && time.length > 0) {
    charts.push({
      kind: 'time',
      title: CHART_TITLES.time,
      metricIds: ['time.machine'],
      unit: 'seconds',
      rows: time,
    });
  }
  return charts;
}

export function seriesKey(entries: Entries, chart: RunChart, hasShare: boolean): string {
  const label = (id: string): string => entries[id]?.label ?? id;
  if (chart.kind === 'bar') return label(chart.metricIds[0]);
  if (chart.kind === 'time') {
    return entries['time.parked']
      ? `${label('time.machine')} · hatched = ${label('time.parked')}`
      : label('time.machine');
  }
  const base = `${label('cost.gateway')} · ${label('cost.harness')}`;
  return hasShare && entries['cost.retries']
    ? `${base} · hatched = ${label('cost.retries')}`
    : base;
}
