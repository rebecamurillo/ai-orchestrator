import type { components } from '../../src/api/schema';
import type { OriginTarget } from '../../src/stores/metric-ui';

export type Entry = components['schemas']['CatalogueEntryOut'];
export type MetricValue = components['schemas']['MetricValueOut'];
export type Version = components['schemas']['ResultVersionOut'];

export const RUN_ID = '0190aaaa-0000-7000-8000-000000000001';
export const PROJECT_ID = '0190aaaa-0000-7000-8000-000000000002';

export function entry(id = 'cost.total', over: Partial<Entry> = {}): Entry {
  return {
    additive: true,
    component_of: null,
    fingerprint_group: false,
    group: 'cost',
    id,
    label: `label of ${id}`,
    level: 'H',
    limits: null,
    methods: [
      { description: `how ${id} v1`, n: 1, parameters: {} },
      { description: `how ${id} v2`, n: 2, parameters: {} },
    ],
    missing_words: ['not recorded', 'not available'],
    scopes: ['run'],
    source: `source of ${id}`,
    unit: 'USD',
    ...over,
  };
}

export function value(over: Partial<MetricValue> = {}): MetricValue {
  return {
    attempt_n: null,
    carried_from: null,
    method_id: 'cost.total@2',
    metric_id: 'cost.total',
    missing: null,
    model: null,
    origin: {
      base_commit: 'b'.repeat(40),
      base_commit_na: null,
      branch: 'feat/x',
      branch_na: null,
      commit: 'c'.repeat(40),
      commit_na: null,
      harness: 'claude',
      harness_na: null,
      origin_model: null,
      origin_model_na: 'spans_models',
      origin_repository: 'acme/app',
      origin_repository_na: null,
      project_id: PROJECT_ID,
      run_id: RUN_ID,
      template_name: 'story',
      template_version: 3,
    },
    partial_m: null,
    partial_n: null,
    repository: null,
    role: null,
    scope_key: RUN_ID,
    scope_label: null,
    scope_type: 'run',
    source: null,
    unit: 'USD',
    value_num: '15.345',
    ...over,
  };
}

export function version(n: number, over: Partial<Version> = {}): Version {
  return {
    calculated_at: '2026-11-19T14:02:00Z',
    entry_point: ['at_attempt_end', 'workflow_step'],
    methods_changed: [],
    n,
    ...over,
  };
}

export function target(over: Partial<OriginTarget> = {}): OriginTarget {
  return {
    value: value(),
    runLabel: 'Run 7',
    version: version(3),
    latest: 3,
    spans: { models: 2 },
    ...over,
  };
}
