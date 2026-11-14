import { entry, type Entry } from './metrics-fixtures';
import {
  A,
  B,
  cell,
  comparePayload,
  header,
  type Cell,
  type CompareMetric,
  type CompareOut,
} from './metrics-compare-fixtures';

export const UNITS: Record<string, string> = {
  'cost.gateway': 'USD',
  'cost.harness': 'USD',
  'time.machine': 'seconds',
  'time.parked': 'seconds',
  'process.attempts': 'count',
  'process.retries': 'count',
  'tokens.output': 'tokens',
  'tokens.cache_read': 'tokens',
  'tokens.cache_hit_share': 'ratio',
  'activity.messages_session': 'count',
  'activity.messages_subagents': 'count',
  'activity.pauses_over_cache_lifetime': 'count',
};

export function entries(ids: string[] = Object.keys(UNITS)): Record<string, Entry> {
  return Object.fromEntries(
    ids.map((id) => [id, entry(id, { unit: UNITS[id] ?? 'count', label: `label of ${id}` })]),
  );
}

export const mcell = (over: Partial<Cell> = {}): Cell => cell({ unit: 'count', ...over });

/** One metric whose cells per Run are given directly. */
export function metricOf(
  id: string,
  cells: Record<string, Cell[]>,
  over: Partial<CompareMetric> = {},
): CompareMetric {
  return {
    cells,
    families: [],
    harness_delta: {},
    methods: {},
    methods_differ: false,
    metric_id: id,
    ...over,
  } as CompareMetric;
}

export function runValueMetric(id: string, ids: string[], values: string[], over = {}) {
  return metricOf(
    id,
    Object.fromEntries(
      ids.map((rid, i) => [
        rid,
        [
          mcell({
            scope_key: rid,
            value_num: values[i],
            unit: UNITS[id] ?? 'count',
            method_id: `${id}@1`,
          }),
        ],
      ]),
    ),
    over,
  );
}

export function payloadOf(metrics: CompareMetric[], ids: string[] = [A, B]): CompareOut {
  return { ...comparePayload(ids), metrics };
}

export const roleCell = (role: string, value: string | null, over: Partial<Cell> = {}): Cell =>
  mcell({ scope_type: 'role', scope_key: role, role, value_num: value, ...over });

export const attemptCell = (role: string, step: string, n: number): Cell =>
  mcell({ scope_type: 'attempt', scope_key: `${step}#${n}`, role, attempt_n: n, value_num: '1' });

export { A, B, header, comparePayload };
