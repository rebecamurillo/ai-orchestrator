/**
 * Chart models of the comparison, drawn on screen and in the PNG. Every figure, word and flag is
 * the payload's: this module orders, groups and names rows, and does no arithmetic (RM-7).
 */
import type { components } from '../../api/schema';
import { NO_CELL, runCells, type CompareState } from '../metrics/compare';
import { NO_SUCH_STEP, runNames, sharedWords } from './compare-runs';
import { isStaticSpec, markToolVersions, staticMark } from './compare-static-charts';
import { unitWords } from './export';
import { niceTicks, type Ticks } from './layout';
import { NO_MODEL_GATEWAY, roleOrder } from './run-charts';

type CompareOut = components['schemas']['CompareOut'];
type CompareCellOut = components['schemas']['CompareCellOut'];
type CompareMetricOut = components['schemas']['CompareMetricOut'];
type FamilyCellOut = components['schemas']['FamilyCellOut'];
type MetricValueOut = components['schemas']['MetricValueOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];
type Entries = Record<string, CatalogueEntryOut>;
type MetricSet = CompareState['set'];

export interface CompareMark {
  value: MetricValueOut | null;
  word?: string;
  dotted?: string;
  share?: MetricValueOut | null;
  rate?: string;
  outline?: true;
}
export interface CompareRow {
  id: string;
  runId: string;
  name: string[];
  marks: [CompareMark, CompareMark?];
}
export interface CompareGroup {
  name: string | null;
  rows: CompareRow[];
}
export interface CompareChart {
  kind: 'dot' | 'bar' | 'pair';
  title: string;
  metricIds: string[];
  unit: string;
  groups: CompareGroup[];
  axisFromZero: boolean;
  flag: string | null;
  context: string[];
  second?: 'hatch';
}

const AXIS_NOTE = 'axis does not start at zero';
const COST = ['cost.gateway', 'cost.harness'];

interface TotalSpec {
  title: string;
  kind: CompareChart['kind'];
  ids: string[];
  share?: string;
  second?: 'hatch';
  all?: true;
  source?: string;
  rate?: string;
}
export const TOTAL_CHARTS: TotalSpec[] = [
  { title: 'cost · gateway and harness', kind: 'dot', ids: COST },
  {
    title: 'machine time · waiting on you',
    kind: 'pair',
    ids: ['time.machine', 'time.parked'],
    second: 'hatch',
  },
  {
    title: 'attempts · of which retries',
    kind: 'bar',
    ids: ['process.attempts'],
    share: 'process.retries',
  },
  { title: 'output tokens', kind: 'bar', ids: ['tokens.output'] },
  { title: 'cache read tokens', kind: 'bar', ids: ['tokens.cache_read'] },
  { title: 'cache hit share', kind: 'bar', ids: ['tokens.cache_hit_share'], all: true },
  {
    title: 'method fingerprint · messages, session and subagents',
    kind: 'pair',
    ids: ['activity.messages_session', 'activity.messages_subagents'],
    all: true,
  },
  {
    title: 'method fingerprint · pauses over cache lifetime',
    kind: 'bar',
    ids: ['activity.pauses_over_cache_lifetime'],
    all: true,
  },
  {
    title: 'type escapes in tests · per 100 test lines',
    kind: 'bar',
    ids: ['code.type_escapes_added'],
    source: 'test',
    rate: 'test:per_100',
  },
  { title: 'duplicated lines added', kind: 'bar', ids: ['code.duplication_added'], all: true },
  { title: 'suppressions added', kind: 'bar', ids: ['code.suppressions_added'], all: true },
  {
    title: 'skip and focus markers added',
    kind: 'bar',
    ids: ['code.skip_focus_markers_added'],
    all: true,
  },
  {
    title: 'test lines added · unit',
    kind: 'bar',
    ids: ['code.test_lines'],
    source: 'test_unit:added',
    rate: 'test_unit:added:per_100',
    all: true,
  },
  {
    title: 'test lines added · e2e',
    kind: 'bar',
    ids: ['code.test_lines'],
    source: 'test_e2e:added',
    rate: 'test_e2e:added:per_100',
    all: true,
  },
];

export const asValue = (cell: CompareCellOut, metricId: string): MetricValueOut => ({
  ...cell,
  metric_id: metricId,
  origin: null,
});

export function familyValue(
  cell: FamilyCellOut,
  metricId: string,
  family: string,
  unit: string,
): MetricValueOut {
  return {
    attempt_n: null,
    carried_from: null,
    method_id: '',
    metric_id: metricId,
    missing: cell.value_num === null ? cell.missing : null,
    model: null,
    origin: null,
    partial_m: null,
    partial_n: null,
    repository: null,
    role: null,
    scope_key: family,
    scope_label: null,
    scope_type: 'role',
    source: null,
    unit,
    value_num: cell.value_num,
  };
}

const metricOf = (payload: CompareOut, id: string): CompareMetricOut | undefined =>
  payload.metrics.find((m) => m.metric_id === id);
const indexOf = (payload: CompareOut, id: string): number =>
  payload.metrics.findIndex((m) => m.metric_id === id);

function markOf(cell: CompareCellOut | undefined, id: string): CompareMark {
  if (cell === undefined) return { value: null, word: NO_CELL };
  if (cell.value_num === null) return { value: null, word: cell.missing ?? NO_CELL };
  return { value: asValue(cell, id) };
}

function cellsAt(
  payload: CompareOut,
  id: string,
  runId: string,
  type: 'role' | 'model',
  key: string,
): CompareCellOut[] {
  const metric = metricOf(payload, id);
  return (metric?.cells[runId] ?? []).filter((c) => c.scope_type === type && c.scope_key === key);
}

const entriesHave = (entries: Entries, ids: string[]): boolean => ids.every((id) => entries[id]);

function shape(spec: { ids: string[]; kind: CompareChart['kind'] }, unit: string) {
  return { kind: spec.kind, metricIds: spec.ids, unit };
}

export function totalCharts(payload: CompareOut, entries: Entries, set: MetricSet): CompareChart[] {
  const names = runNames(payload.runs);
  const shared = sharedWords(payload.runs.map((h) => h.label)).join(' ');
  const specs = TOTAL_CHARTS.filter(
    (s) => (set === 'all' || !s.all) && entriesHave(entries, s.ids) && metricOf(payload, s.ids[0]),
  ).sort((a, b) => indexOf(payload, a.ids[0]) - indexOf(payload, b.ids[0]));
  return specs.map((spec) => {
    const primary = metricOf(payload, spec.ids[0]) as CompareMetricOut;
    const unit = entries[spec.ids[0]].unit;
    const stat = isStaticSpec(spec);
    const differs =
      spec.kind !== 'dot' && primary.methods_differ && !(stat && primary.tool_versions_differ);
    const methods = payload.runs.map((h) => primary.methods[h.run_id] ?? []);
    const base = JSON.stringify(methods[0]);
    const rows: CompareRow[] = payload.runs.map((h, i) => {
      const marks = spec.ids.map((id) => {
        const metric = metricOf(payload, id);
        if (stat && metric !== undefined) return staticMark(payload, metric, spec, h.run_id);
        return metric === undefined
          ? { value: null, word: NO_CELL }
          : markOf(runCells(metric, h.run_id)[0], id);
      });
      if (spec.share !== undefined) {
        const retries = metricOf(payload, spec.share);
        const cell = retries && runCells(retries, h.run_id)[0];
        if (cell && cell.value_num !== null) marks[0].share = asValue(cell, spec.share);
      }
      if (differs && JSON.stringify(methods[i]) !== base) marks[0].dotted = methods[i].join(', ');
      return {
        id: h.run_id,
        runId: h.run_id,
        name: names[i].lines,
        marks: marks as CompareRow['marks'],
      };
    });
    const toolFlagged = stat ? markToolVersions(payload, primary, rows) : null;
    const line = [unitWords(unit), ...(spec.kind === 'dot' ? [AXIS_NOTE] : [])].join(' · ');
    const distinct = [...new Set(methods.flat())].sort();
    return {
      ...shape(spec, unit),
      title: spec.title,
      groups: [{ name: null, rows }],
      axisFromZero: spec.kind !== 'dot',
      flag: toolFlagged ?? (differs ? `≠ methods differ: ${distinct.join(' · ')}` : null),
      context: [...(shared === '' ? [] : [shared]), line],
      ...(spec.second ? { second: spec.second } : {}),
    };
  });
}

export function roleOrderAcross(
  payload: CompareOut,
  metricId: string,
  stepOrder: readonly string[],
): string[] {
  const items = (runId: string): MetricValueOut[] =>
    (metricOf(payload, metricId)?.cells[runId] ?? []).map((c) => asValue(c, metricId));
  const [first, ...later] = payload.runs;
  if (first === undefined) return [];
  const order = roleOrder(items(first.run_id), stepOrder);
  for (const h of later) {
    for (const role of roleOrder(items(h.run_id), [])) if (!order.includes(role)) order.push(role);
  }
  return order;
}

const BREAKDOWN_CHARTS: TotalSpec[] = [
  { title: 'cost by role · gateway and harness', kind: 'pair', ids: COST },
  { title: 'output tokens by role', kind: 'bar', ids: ['tokens.output'] },
  { title: 'cache read tokens by role', kind: 'bar', ids: ['tokens.cache_read'] },
];

const eligible = (payload: CompareOut, entries: Entries): TotalSpec[] =>
  BREAKDOWN_CHARTS.filter(
    (s) => entriesHave(entries, s.ids) && s.ids.some((id) => metricOf(payload, id)),
  );

export function roleCharts(
  payload: CompareOut,
  entries: Entries,
  stepOrder: readonly string[],
): CompareChart[] {
  const out: CompareChart[] = [];
  for (const spec of eligible(payload, entries)) {
    const present = spec.ids.filter((id) => metricOf(payload, id));
    const roles = roleOrderAcross(payload, present[0], stepOrder);
    for (const id of present) {
      for (const h of payload.runs) {
        for (const c of metricOf(payload, id)?.cells[h.run_id] ?? []) {
          if (c.scope_type === 'role' && !roles.includes(c.scope_key)) roles.push(c.scope_key);
        }
      }
    }
    let any = false;
    const groups = roles.map((role) => ({
      name: role,
      rows: payload.runs.map((h, i): CompareRow => {
        const found = spec.ids.map((id) => cellsAt(payload, id, h.run_id, 'role', role)[0]);
        const name = [`R${i + 1}`];
        const row = { id: `${role}:${h.run_id}`, runId: h.run_id, name };
        if (found.every((c) => c === undefined)) {
          return { ...row, marks: [{ value: null, word: NO_SUCH_STEP }] };
        }
        any = true;
        return {
          ...row,
          marks: spec.ids.map((id, n) => markOf(found[n], id)) as CompareRow['marks'],
        };
      }),
    }));
    if (!any) continue;
    const unit = entries[spec.ids[0]].unit;
    out.push({
      ...shape(spec, unit),
      title: spec.title,
      groups,
      axisFromZero: true,
      flag: null,
      context: [unitWords(unit)],
    });
  }
  return out;
}

export function modelCharts(payload: CompareOut, entries: Entries): CompareChart[] {
  const specs: { title: string; ids: string[]; kind: CompareChart['kind']; note?: string }[] = [];
  const split = payload.metrics.some(
    (m) =>
      m.metric_id === 'cost.gateway' &&
      Object.values(m.cells).some((cs) => cs.some((c) => c.scope_type === 'model')),
  );
  specs.push(
    split
      ? { title: 'cost by model · gateway and harness', ids: COST, kind: 'pair' }
      : {
          title: 'cost by model · harness',
          ids: ['cost.harness'],
          kind: 'bar',
          note: NO_MODEL_GATEWAY,
        },
    { title: 'output tokens by model', ids: ['tokens.output'], kind: 'bar' },
  );
  const out: CompareChart[] = [];
  for (const spec of specs) {
    if (!entriesHave(entries, spec.ids)) continue;
    const models: string[] = [];
    for (const id of spec.ids) {
      for (const h of payload.runs) {
        for (const c of metricOf(payload, id)?.cells[h.run_id] ?? []) {
          if (c.scope_type === 'model' && !models.includes(c.scope_key)) models.push(c.scope_key);
        }
      }
    }
    if (models.length === 0) continue;
    const groups = models.map((model) => ({
      name: model,
      rows: payload.runs.flatMap((h, i): CompareRow[] => {
        const lists = spec.ids.map((id) => cellsAt(payload, id, h.run_id, 'model', model));
        const count = Math.max(1, ...lists.map((l) => l.length));
        return Array.from({ length: count }, (_, n) => ({
          id: `${model}:${h.run_id}:${n}`,
          runId: h.run_id,
          name: [`R${i + 1}`],
          marks: spec.ids.map((id, k) => markOf(lists[k][n], id)) as CompareRow['marks'],
        }));
      }),
    }));
    const unit = entries[spec.ids[0]].unit;
    out.push({
      ...shape(spec, unit),
      title: spec.title,
      groups,
      axisFromZero: true,
      flag: null,
      context: [unitWords(unit), ...(spec.note ? [spec.note] : [])],
    });
  }
  return out;
}

export function familyCharts(payload: CompareOut, entries: Entries): CompareChart[] {
  const out: CompareChart[] = [];
  for (const spec of eligible(payload, entries)) {
    const present = spec.ids.filter((id) => metricOf(payload, id));
    const families = [
      ...new Set(
        present.flatMap((id) => (metricOf(payload, id)?.families ?? []).map((f) => f.family)),
      ),
    ];
    if (families.length === 0) continue;
    const unit = entries[spec.ids[0]].unit;
    const differing: string[] = [];
    const groups = families.map((family) => ({
      name: family,
      rows: payload.runs.map((h, i): CompareRow => {
        const marks = spec.ids.map((id): CompareMark => {
          const f = metricOf(payload, id)?.families.find((x) => x.family === family);
          const cell = f?.cells[h.run_id];
          if (f?.step_structure_differs && !differing.includes(family)) differing.push(family);
          if (cell === undefined) return { value: null, word: NO_CELL };
          if (cell.value_num === null) return { value: null, word: cell.missing ?? NO_CELL };
          const value = familyValue(cell, id, family, entries[id].unit);
          return cell.missing === 'partial' ? { value, outline: true } : { value };
        });
        return {
          id: `${family}:${h.run_id}`,
          runId: h.run_id,
          name: [`R${i + 1}`],
          marks: marks as CompareRow['marks'],
        };
      }),
    }));
    const detail = differing.map((family) => {
      const f = present
        .flatMap((id) => metricOf(payload, id)?.families ?? [])
        .find((x) => x.family === family && x.step_structure_differs);
      const runs = payload.runs.flatMap((h, i) => {
        const cell = f?.cells[h.run_id];
        return cell === undefined ? [] : [`R${i + 1} ${cell.roles.join(' · ')}`];
      });
      return `${family}: ${runs.join('; ')}`;
    });
    out.push({
      ...shape(spec, unit),
      title: `${spec.title} · role family`,
      groups,
      axisFromZero: true,
      flag: detail.length === 0 ? null : `≠ step structure differs · ${detail.join(' · ')}`,
      context: [unitWords(unit)],
    });
  }
  return out;
}

export interface ChartOptions {
  breakdown: 'total' | 'role' | 'model';
  roles: 'declared' | 'family';
  set: MetricSet;
  stepOrder: readonly string[];
}

export function chartsFor(
  payload: CompareOut,
  entries: Entries,
  opts: ChartOptions,
): CompareChart[] {
  if (opts.breakdown === 'total') return totalCharts(payload, entries, opts.set);
  if (opts.breakdown === 'model') return modelCharts(payload, entries);
  return opts.roles === 'family'
    ? familyCharts(payload, entries)
    : roleCharts(payload, entries, opts.stepOrder);
}

export function rangeTicks(min: number, max: number): Ticks & { origin: number } {
  let lo = min;
  let hi = max;
  if (hi - lo <= 0) {
    const step = niceTicks(0).step;
    lo -= step;
    hi += step;
  }
  const { step } = niceTicks(hi - lo);
  const origin = Math.max(0, Math.floor(lo / step + 1e-9) * step);
  const ticks = [origin];
  while (ticks[ticks.length - 1] < hi - 1e-9) {
    ticks.push(Number((ticks[ticks.length - 1] + step).toFixed(10)));
  }
  return { step, ticks, origin };
}
