import type { components } from '../../src/api/schema';

export type CompareOut = components['schemas']['CompareOut'];
export type Header = components['schemas']['CompareRunHeaderOut'];
export type CompareMetric = components['schemas']['CompareMetricOut'];
export type Cell = components['schemas']['CompareCellOut'];

export const A = 'aaaaaaaa-0000-7000-8000-000000000001';
export const B = 'bbbbbbbb-0000-7000-8000-000000000002';
export const C = 'cccccccc-0000-7000-8000-000000000003';
export const PROJECT = 'pppppppp-0000-7000-8000-000000000009';

export function header(id: string, over: Partial<Header> = {}): Header {
  return {
    base_branch: 'main',
    harness: 'claude',
    label: `label ${id.slice(0, 1)}`,
    label_set_by_operator: false,
    models_by_role: { coder: ['m1', 'm2'] },
    run_id: id,
    selected_version: 2,
    short_id: id.slice(0, 8),
    status: 'done',
    stories_done: { done: 3, planned: 4 },
    subscription: null,
    template_name: 'story',
    template_version: '3',
    versions_available: [2, 1],
    ...over,
  };
}

export function cell(over: Partial<Cell> = {}): Cell {
  return {
    attempt_n: null,
    carried_from: null,
    method_id: 'cost.gateway@1',
    missing: null,
    model: null,
    partial_m: null,
    partial_n: null,
    repository: null,
    role: null,
    scope_key: A,
    scope_label: null,
    scope_type: 'run',
    source: null,
    unit: 'USD',
    value_num: '1.5',
    ...over,
  };
}

export function metric(metricId: string, ids: string[], over: Partial<CompareMetric> = {}) {
  return {
    cells: Object.fromEntries(
      ids.map((id) => [id, [cell({ scope_key: id, method_id: `${metricId}@1` })]]),
    ),
    families: [],
    harness_delta: {},
    methods: {},
    methods_differ: false,
    metric_id: metricId,
    ...over,
  } as CompareMetric;
}

export function comparePayload(
  ids: string[] = [A, B, C],
  over: Partial<CompareOut> = {},
): CompareOut {
  return {
    diff_size: Object.fromEntries(ids.map((id) => [id, 'not run'])),
    metrics: [metric('cost.gateway', ids), metric('tokens.input', ids), metric('time.wall', ids)],
    project_id: PROJECT,
    project_name: 'Proj',
    runs: ids.map((id) => header(id)),
    same_work: {
      differs: false,
      runs: Object.fromEntries(
        ids.map((id) => [
          id,
          {
            base_commits: { 'acme/app': 'abcdef0123456789' },
            initiative_folder: 'init',
            stories_planned: 4,
          },
        ]),
      ),
    },
    ...over,
  };
}
