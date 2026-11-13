/**
 * Wording and shaping for the comparison page. Every figure, flag, delta and label is the
 * API's, printed as given; the only derivations here are layout (grouping by catalogue
 * `group`, the headline filter by `level`) and the blind template collapse (RM-7).
 */
import type { components } from '../../api/schema';
import type { OriginTarget } from '../../stores/metric-ui';
import { TAB_GROUPS } from '../run/metrics-tab';
import { metricsHref, runToken } from './home';

type CompareOut = components['schemas']['CompareOut'];
type CompareRunHeaderOut = components['schemas']['CompareRunHeaderOut'];
type CompareMetricOut = components['schemas']['CompareMetricOut'];
type CompareCellOut = components['schemas']['CompareCellOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

export const COMPARE_TITLE = 'COMPARE';
export const TOO_FEW_LINE = 'select at least two Runs of one project in Metrics';
export const METHODS_DIFFER = '≠ methods differ';
export const WORK_DIFFERS = '≠ the work differs';
export const SAME_WORK_LABEL = 'same work?';
export const SAME_WORK_SUB = 'base commit · initiative · stories planned';
export const DIFF_SIZE_LABEL = 'diff size';
export const NOT_RUN_WORD = 'not run';
export const RECALC_WORD = 'recalculate';
export const REMOVE_WORD = 'remove';
export const ADD_RUNS_WORD = 'add runs';
export const BLIND_WORD = 'blind';
export const EXPORT_LABEL = 'EXPORT CSV + JSON';
export const HIDDEN_WORD = 'hidden · blind';
export const NO_CELL = '—';
export const STATIC_GROUP = 'STATIC SIGNALS ON THE CHANGE';

export interface CompareState {
  runIds: string[];
  versions: Record<string, number>;
  view: 'table' | 'chart';
  set: 'headline' | 'all';
  blind: boolean;
}

export function parseCompare(search: string): CompareState {
  const q = new URLSearchParams(search);
  const runIds: string[] = [];
  for (const part of (q.get('runs') ?? '').split(',')) {
    const id = part.trim();
    if (id !== '' && !runIds.includes(id)) runIds.push(id);
  }
  const versions: Record<string, number> = {};
  for (const token of (q.get('v') ?? '').split(',')) {
    const at = token.lastIndexOf(':');
    const id = token.slice(0, at);
    const n = token.slice(at + 1);
    if (at > 0 && runIds.includes(id) && /^[1-9]\d*$/.test(n) && Number.isSafeInteger(Number(n))) {
      versions[id] = Number(n);
    }
  }
  return {
    runIds,
    versions,
    view: q.get('view') === 'chart' ? 'chart' : 'table',
    set: q.get('metrics') === 'all' ? 'all' : 'headline',
    blind: q.get('blind') === '1',
  };
}

function versionPairs(state: CompareState): string {
  return state.runIds
    .filter((id) => state.versions[id] !== undefined)
    .map((id) => `${id}:${state.versions[id]}`)
    .join(',');
}

export function compareSearch(state: CompareState): string {
  const pairs = versionPairs(state);
  return (
    `?runs=${state.runIds.join(',')}` +
    (pairs === '' ? '' : `&v=${pairs}`) +
    (state.view === 'chart' ? '&view=chart' : '') +
    (state.set === 'all' ? '&metrics=all' : '') +
    (state.blind ? '&blind=1' : '')
  );
}

export function compareQuery(state: CompareState): { runs: string; v?: string; blind?: true } {
  const pairs = versionPairs(state);
  return {
    runs: state.runIds.join(','),
    ...(pairs === '' ? {} : { v: pairs }),
    ...(state.blind ? { blind: true as const } : {}),
  };
}

export function removeRun(state: CompareState, id: string): CompareState {
  const versions = { ...state.versions };
  delete versions[id];
  return { ...state, runIds: state.runIds.filter((r) => r !== id), versions };
}

export function setVersion(
  state: CompareState,
  id: string,
  n: number,
  latest: number | null,
): CompareState {
  const versions = { ...state.versions };
  if (n === latest) delete versions[id];
  else versions[id] = n;
  return { ...state, versions };
}

export const addRunsHref = (projectId: string, runIds: readonly string[]): string =>
  metricsHref(projectId, runIds);

export const recalcHref = (id: string): string => `/workflows/${id}?tab=metrics&recalculate=1`;

export interface HeaderView {
  id: string;
  token: string;
  shortId: string;
  href: string;
  label: string;
  ownLabel: boolean;
  template: string;
  harness: string;
  models: string[];
  base: string;
  status: string;
  stories: string | null;
  versions: number[];
  selected: number | null;
  latest: number | null;
}

export function headerView(h: CompareRunHeaderOut): HeaderView {
  const versions = [...h.versions_available].sort((a, b) => a - b);
  return {
    id: h.run_id,
    token: runToken(h.status),
    shortId: h.short_id,
    href: `/workflows/${h.run_id}`,
    label: h.label,
    ownLabel: h.label_set_by_operator,
    template:
      h.template_name === HIDDEN_WORD && h.template_version === HIDDEN_WORD
        ? HIDDEN_WORD
        : `${h.template_name}@${h.template_version}`,
    harness: h.harness ?? '—',
    models: Object.entries(h.models_by_role).map(([role, ms]) => `${role}: ${ms.join(' · ')}`),
    base: `base ${h.base_branch ?? '—'}`,
    status: h.status,
    stories: h.stories_done ? `${h.stories_done.done}/${h.stories_done.planned} stories` : null,
    versions,
    selected: h.selected_version,
    latest: versions.length === 0 ? null : versions[versions.length - 1],
  };
}

export interface SameWorkView {
  flag: string | null;
  cells: Record<string, { commits: string; initiative: string; stories: string }>;
}

export function sameWorkView(payload: CompareOut): SameWorkView {
  const cells: SameWorkView['cells'] = {};
  for (const h of payload.runs) {
    const work = payload.same_work.runs[h.run_id];
    cells[h.run_id] = work
      ? {
          commits:
            Object.entries(work.base_commits)
              .map(([repo, commit]) => `${repo}:${commit === null ? '—' : commit.slice(0, 8)}`)
              .join(' ') || '—',
          initiative: work.initiative_folder ?? '—',
          stories: work.stories_planned === null ? '—' : String(work.stories_planned),
        }
      : { commits: '—', initiative: '—', stories: '—' };
  }
  return { flag: payload.same_work.differs ? WORK_DIFFERS : null, cells };
}

export function groupRows(
  entries: Record<string, CatalogueEntryOut>,
  metrics: readonly CompareMetricOut[],
  set: CompareState['set'],
): { group: string; rows: CompareMetricOut[] }[] {
  const groups = new Map<string, CompareMetricOut[]>(TAB_GROUPS.map(([name]) => [name, []]));
  for (const m of metrics) {
    const entry = entries[m.metric_id];
    if (!entry || (set === 'headline' && entry.level !== 'H')) continue;
    const name = TAB_GROUPS.find(([, ids]) => ids.includes(entry.group))?.[0];
    if (name) groups.get(name)?.push(m);
  }
  return [...groups].map(([group, rows]) => ({ group, rows })).filter((g) => g.rows.length > 0);
}

export const runCells = (metric: CompareMetricOut, runId: string): CompareCellOut[] =>
  (metric.cells[runId] ?? []).filter((c) => c.scope_type === 'run');

export const methodsLine = (metric: CompareMetricOut, runId: string): string | null =>
  metric.methods_differ ? (metric.methods[runId] ?? []).join(', ') : null;

export const deltaOf = (metric: CompareMetricOut, runId: string): string | null =>
  metric.harness_delta[runId] ?? null;

export function cellTarget(
  cell: CompareCellOut,
  metricId: string,
  header: CompareRunHeaderOut,
): OriginTarget {
  return {
    value: { ...cell, metric_id: metricId, origin: null },
    runLabel: header.label,
    version: null,
    latest: header.selected_version,
    subscription: header.subscription === true,
  };
}

export function fileNameOf(disposition: string | null, fallback: string): string {
  return /filename="([^"]+)"/.exec(disposition ?? '')?.[1] ?? fallback;
}

export const exportLine = (base: string, runs: number, metrics: number, blind: boolean): string =>
  `exported ${base}.csv and .json · ${runs} Runs · ${metrics} metrics · ` +
  `${blind ? 'run labels hidden' : 'run labels included'} · each description once`;

export const exportFailedLine = (path: string, status: number | string): string =>
  `export failed · GET ${path} · ${status}`;
