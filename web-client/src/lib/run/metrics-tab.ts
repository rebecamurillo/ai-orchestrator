/**
 * Every string and ordering the METRICS tab prints is built here; components only place them.
 * Labels, descriptions and missing words come from the catalogue and the API, never from this
 * file (RM-2). The frame helpers mirror `application/rules/frames.py`.
 */
import type { components } from '../../api/schema';
import { isEnded } from './metrics-glance';

type MetricValueOut = components['schemas']['MetricValueOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

export const TABLE_COLUMNS = [
  'cost.gateway',
  'cost.harness',
  'tokens.input',
  'tokens.output',
  'tokens.cache_read',
  'tokens.cache_write',
  'time.wall',
  'process.attempts',
  'process.retries',
  'process.failures',
] as const;

export const ATTEMPT_COLUMNS = TABLE_COLUMNS.slice(0, 6);

export const TAB_GROUPS: readonly (readonly [string, readonly string[]])[] = [
  ['COST', ['cost', 'budget', 'spend']],
  ['TOKENS', ['tokens']],
  ['TIME', ['time']],
  ['PROCESS', ['process']],
  ['ACTIVITY IN ATTEMPTS', ['activity']],
];

export const FINGERPRINT_LINE = 'describes how the method works, not how well';
export const LIVE_LINE = 'Run running · values so far, stored as each attempt ends';
export const NO_VERSION_LINE =
  'no result version · CALCULATE METRICS creates v1; metrics only the deleted logs held will read not recorded';
export const NO_ATTEMPTS = 'no attempts yet';
export const VIEW_LABELS = { table: 'TABLE', chart: 'CHART' } as const;
export const SET_LABELS = { headline: 'HEADLINE', all: 'ALL METRICS' } as const;

export type MetricsView = keyof typeof VIEW_LABELS;
export type MetricsSet = keyof typeof SET_LABELS;
export type TabName = 'gate' | 'steps' | 'session' | 'metrics';

const SEGMENT = /^([^.[\]]+)\[(\d+)\]$/;

function prefixThrough(path: string, name: string): string | null {
  const segments = path.split('.');
  for (let i = segments.length - 1; i >= 0; i -= 1) {
    const match = SEGMENT.exec(segments[i]);
    if (match && match[1] === name) return segments.slice(0, i + 1).join('.');
  }
  return null;
}

export const storyFrame = (path: string): string | null => prefixThrough(path, 'stories');
export const epicFrame = (path: string): string | null => prefixThrough(path, 'epics');

export function valuesAt(
  items: readonly MetricValueOut[],
  metricId: string,
  scopeType: string,
  scopeKey: string,
): MetricValueOut[] {
  return items.filter(
    (v) => v.metric_id === metricId && v.scope_type === scopeType && v.scope_key === scopeKey,
  );
}

export interface ScopeNode {
  id: string;
  type: string;
  key: string;
  label: string;
  children: ScopeNode[];
}

const TREE_TYPES = ['run', 'epic', 'story', 'step', 'attempt'];

/** The index a frame or step carries as its last `[i]` segment. */
function lastIndex(key: string): number {
  const match = /\[(\d+)\][^[]*$/.exec(key);
  return match ? Number(match[1]) : 0;
}

function epicLabel(key: string): string {
  return `epic ${lastIndex(key) + 1}`;
}

function attemptNumber(key: string, v: MetricValueOut | undefined): string {
  return String(v?.attempt_n ?? key.slice(key.lastIndexOf('#') + 1));
}

function labelOf(type: string, key: string, v: MetricValueOut | undefined): string {
  const given = v?.scope_label ?? null;
  if (type === 'epic') return epicLabel(key);
  if (type === 'story') {
    const own = `story ${given ?? lastIndex(key) + 1}`;
    const epic = epicFrame(key);
    return epic === null ? own : `${epicLabel(epic)} · ${own}`;
  }
  if (type === 'step') return given ?? key;
  if (type === 'attempt') return `attempt ${attemptNumber(key, v)}`;
  return 'run';
}

function parentOf(type: string, key: string): { type: string; key: string } {
  if (type === 'attempt') {
    return { type: 'step', key: key.slice(0, Math.max(0, key.lastIndexOf('#'))) };
  }
  const story = type === 'step' ? storyFrame(key) : null;
  if (story !== null) return { type: 'story', key: story };
  const epic = type === 'step' || type === 'story' ? epicFrame(key) : null;
  if (epic !== null) return { type: 'epic', key: epic };
  return { type: 'run', key: '' };
}

export function scopeTree(
  items: readonly MetricValueOut[],
  stepOrder: readonly string[],
): ScopeNode {
  const root: ScopeNode = { id: 'run:', type: 'run', key: '', label: 'run', children: [] };
  const nodes = new Map<string, ScopeNode>([[root.id, root]]);
  root.key = items.find((v) => v.scope_type === 'run')?.scope_key ?? '';
  const sample = new Map<string, MetricValueOut>();
  for (const v of items) {
    if (!TREE_TYPES.includes(v.scope_type) || v.scope_type === 'run') continue;
    const id = `${v.scope_type}:${v.scope_key}`;
    if (!sample.has(id)) sample.set(id, v);
  }

  function ensure(type: string, key: string): ScopeNode {
    const id = `${type}:${key}`;
    const found = nodes.get(id);
    if (found) return found;
    const node: ScopeNode = {
      id,
      type,
      key,
      label: labelOf(type, key, sample.get(id)),
      children: [],
    };
    nodes.set(id, node);
    const parent = parentOf(type, key);
    (parent.type === 'run' ? root : ensure(parent.type, parent.key)).children.push(node);
    return node;
  }
  for (const id of sample.keys()) {
    const v = sample.get(id) as MetricValueOut;
    ensure(v.scope_type, v.scope_key);
  }

  const rank = (n: ScopeNode): number => {
    if (n.type === 'attempt') return Number(attemptNumber(n.key, sample.get(n.id)));
    const at = stepOrder.findIndex((p) => p === n.key || p.startsWith(`${n.key}.`));
    return at === -1 ? Number.POSITIVE_INFINITY : at;
  };
  for (const node of nodes.values()) {
    node.children.sort((a, b) => {
      const d = rank(a) - rank(b);
      if (Number.isNaN(d)) return a.key < b.key ? -1 : 1;
      return d !== 0 ? d : a.key < b.key ? -1 : a.key > b.key ? 1 : 0;
    });
  }
  return root;
}

export function flatRows(items: readonly MetricValueOut[], scopeType: 'role' | 'model'): string[] {
  const gateway = new Map<string, number | null>();
  for (const v of items) {
    if (v.scope_type !== scopeType) continue;
    if (!gateway.has(v.scope_key)) gateway.set(v.scope_key, null);
    if (v.metric_id === 'cost.gateway' && v.value_num !== null) {
      gateway.set(v.scope_key, Number(v.value_num));
    }
  }
  return [...gateway.keys()].sort((a, b) => {
    const x = gateway.get(a) ?? null;
    const y = gateway.get(b) ?? null;
    if (x === null || y === null) {
      if (x !== y) return x === null ? 1 : -1;
    } else if (x !== y) return y - x;
    return a < b ? -1 : 1;
  });
}

export interface ListEntry {
  entry: CatalogueEntryOut;
  values: MetricValueOut[];
}
export interface ListGroup {
  group: string;
  entries: ListEntry[];
}

export function metricList(
  entries: Record<string, CatalogueEntryOut>,
  items: readonly MetricValueOut[],
  set: MetricsSet,
): ListGroup[] {
  const groups = new Map<string, ListEntry[]>(TAB_GROUPS.map(([name]) => [name, []]));
  const fingerprint: ListEntry[] = [];
  for (const entry of Object.values(entries)) {
    if (set === 'headline' && entry.level !== 'H') continue;
    const values = items.filter((v) => v.scope_type === 'run' && v.metric_id === entry.id);
    if (values.length === 0) continue;
    if (entry.fingerprint_group) {
      if (set === 'all') fingerprint.push({ entry, values });
      continue;
    }
    const name = TAB_GROUPS.find(([, ids]) => ids.includes(entry.group))?.[0];
    if (name) groups.get(name)?.push({ entry, values });
  }
  const list = [...groups].map(([group, rows]) => ({ group, entries: rows }));
  list.push({ group: FINGERPRINT_LINE, entries: fingerprint });
  return list.filter((g) => g.entries.length > 0);
}

const TABS: readonly string[] = ['gate', 'steps', 'session', 'metrics'];

export function parseMetricsQuery(search: string): {
  tab: TabName | null;
  view: MetricsView;
  set: MetricsSet;
  v: number | null;
} {
  const q = new URLSearchParams(search);
  const tab = q.get('tab') ?? '';
  const v = q.get('v') ?? '';
  return {
    tab: TABS.includes(tab) ? (tab as TabName) : null,
    view: q.get('view') === 'chart' ? 'chart' : 'table',
    set: q.get('metrics') === 'all' ? 'all' : 'headline',
    v: /^[1-9]\d*$/.test(v) && Number.isSafeInteger(Number(v)) ? Number(v) : null,
  };
}

/**
 * The selection a `?v=` read settles on once the versions are known: the latest version and a
 * version the Run does not have both become `null` (follow the latest), so neither pins the page.
 */
export function settledVersion(
  selected: number | null,
  versions: readonly { n: number }[],
): number | null {
  if (selected === null || versions.length === 0) return selected;
  const latest = Math.max(...versions.map((v) => v.n));
  return selected === latest || !versions.some((v) => v.n === selected) ? null : selected;
}

export function metricsSearch(
  search: string,
  state: { tab: TabName; view: MetricsView; set: MetricsSet; v: number | null },
): string {
  const q = new URLSearchParams(search);
  q.set('tab', state.tab);
  if (state.tab === 'metrics') {
    q.set('view', state.view);
    if (state.set === 'all') q.set('metrics', 'all');
    else q.delete('metrics');
  } else {
    q.delete('view');
    q.delete('metrics');
  }
  if (state.v === null) q.delete('v');
  else q.set('v', String(state.v));
  const text = q.toString();
  return text === '' ? '' : `?${text}`;
}

export function defaultTab(args: {
  hashSeq: number | null;
  queryTab: TabName | null;
  hasTerminal: boolean;
  status: string;
}): TabName {
  if (args.hashSeq !== null) return 'steps';
  if (args.queryTab !== null && (args.queryTab !== 'session' || args.hasTerminal)) {
    return args.queryTab;
  }
  if (args.hasTerminal) return 'session';
  return isEnded(args.status) ? 'metrics' : 'gate';
}

export function attemptValues(items: readonly MetricValueOut[], path: string): MetricValueOut[] {
  return items.filter((v) => v.scope_type === 'attempt' && v.scope_key.startsWith(`${path}#`));
}
