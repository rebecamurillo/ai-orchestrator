/** Wording and shaping for the Metrics home page. Every figure is the API's, never computed. */
import type { components } from '../../api/schema';
import type { OriginTarget } from '../../stores/metric-ui';
import { formatValue } from './format';

type MetricsRunOut = components['schemas']['MetricsRunOut'];
type ProjectSpendOut = components['schemas']['ProjectSpendOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

export const NO_PROJECT_LINE = 'choose a project above to list its Runs';
export const RUNNING_WORD = 'running';
export const SO_FAR_WORD = 'values so far';
export const OWN_LABEL_WORD = 'your label';
export const NO_VERSION_WORD = 'no result version';

export function monthText(now: Date): string {
  return now.toISOString().slice(0, 7);
}

export function projectsCount(n: number): string {
  return n === 1 ? '1 project' : `${n} projects`;
}

export function parseSelect(raw: string | null): string[] {
  if (!raw) return [];
  const out: string[] = [];
  for (const part of raw.split(',')) {
    const id = part.trim();
    if (id !== '' && !out.includes(id)) out.push(id);
  }
  return out;
}

export function pruneSelection(
  selected: readonly string[],
  runs: readonly MetricsRunOut[],
): string[] {
  const ok = new Set(runs.filter((r) => r.selectable).map((r) => r.id));
  return selected.filter((id) => ok.has(id));
}

export function toggleSelection(selected: readonly string[], id: string): string[] {
  return selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id];
}

export function metricsHref(projectId: string | null, selected: readonly string[]): string {
  if (!projectId) return '/metrics';
  const select = selected.length > 0 ? `&select=${selected.join(',')}` : '';
  return `/metrics?project=${projectId}${select}`;
}

export function compareHref(selected: readonly string[]): string {
  return `/metrics/compare?runs=${selected.join(',')}`;
}

const TOKENS: Record<string, string> = {
  queued: 'QUE',
  running: 'RUN',
  needs_you: 'BLK',
  done: 'DON',
  failed: 'ERR',
  cancelled: 'CAN',
};

export function runToken(status: string): string {
  return TOKENS[status] ?? 'QUE';
}

export interface RunRowView {
  id: string;
  select: 'box' | 'running' | 'none';
  token: string;
  label: string;
  ownLabel: boolean;
  shortId: string;
  href: string;
  template: string;
  harness: string;
  baseBranch: string;
  wallClock: string;
  gateway: string;
  harnessSpend: string;
  version: string;
}

export function runRowView(run: MetricsRunOut): RunRowView {
  const live = run.status === 'running' || run.status === 'needs_you';
  let version = '—';
  if (!run.selectable && live) version = SO_FAR_WORD;
  else if (run.latest_version !== null) version = `v${run.latest_version}`;
  else if (!live && run.status !== 'queued') version = NO_VERSION_WORD;
  return {
    id: run.id,
    select: run.selectable ? 'box' : live ? 'running' : 'none',
    token: runToken(run.status),
    label: run.label,
    ownLabel: run.label_set_by_operator,
    shortId: run.id.slice(0, 8),
    href: `/workflows/${run.id}`,
    template: `${run.template_name}@${run.template_version}`,
    harness: run.harness ?? '—',
    baseBranch: `${run.base_branch ?? '—'} → ${run.branch ?? '—'}`,
    wallClock:
      run.wall_clock_seconds === null
        ? '—'
        : formatValue(String(run.wall_clock_seconds), 'seconds'),
    gateway: formatValue(run.gateway, 'USD'),
    harnessSpend: formatValue(run.harness_spend, 'USD'),
    version,
  };
}

export function orderSpend(
  items: readonly ProjectSpendOut[],
  projectId: string | null,
): ProjectSpendOut[] {
  const chosen = items.filter((i) => i.project_id === projectId);
  return [...chosen, ...items.filter((i) => i.project_id !== projectId)];
}

export function anySubscription(items: readonly ProjectSpendOut[]): boolean {
  return items.some((i) => i.subscription === true);
}

export function spendTarget(
  item: ProjectSpendOut,
  metricId: string,
  valueNum: string,
  entry: CatalogueEntryOut | null,
): OriginTarget {
  const newest = entry ? Math.max(...entry.methods.map((m) => m.n)) : null;
  return {
    value: {
      attempt_n: null,
      carried_from: null,
      method_id: newest === null ? metricId : `${metricId}@${newest}`,
      metric_id: metricId,
      missing: null,
      model: null,
      origin: null,
      partial_m: null,
      partial_n: null,
      repository: null,
      role: null,
      scope_key: item.project_id,
      scope_label: item.project_name,
      scope_type: 'project',
      source: null,
      unit: 'USD',
      value_num: valueNum,
    },
    runLabel: item.project_name,
    projectName: item.project_name,
    version: null,
    latest: null,
    subscription: item.subscription === true,
  };
}
