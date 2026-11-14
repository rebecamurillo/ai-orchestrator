import type { components } from '../../src/api/schema';
import { entry, value, type MetricValue } from './metrics-fixtures';

export type Analysis = components['schemas']['AnalysisOut'];

export const SECRETS = 'code.possible_secrets';
export const DUP = 'code.duplication_added';
export const SUPP = 'code.suppressions_added';

export function analysis(over: Partial<Analysis> = {}): Analysis {
  return {
    analysis_id: 'an-1',
    base: 'b'.repeat(40),
    base_branch: 'main',
    commits_outside_run: 0,
    declaration_hash: 'abcdef123456',
    head: 'h'.repeat(40),
    languages: ['Python', 'CSS'],
    lookup_date: '2026-11-13',
    reason: '',
    repository_path: '.',
    sarif_tools: [],
    status: 'ok',
    tools: [
      { tool: 'gitleaks', version: '8.30.1' },
      { tool: 'jscpd', version: '4.0.5' },
      { tool: 'lizard', version: '1.17' },
      { tool: 'osv-scanner', version: '2.0' },
    ],
    vulnerability_db_date: '2026-11-12',
    ...over,
  };
}

export const code = (id: string, over: Partial<MetricValue> = {}): MetricValue =>
  value({
    metric_id: id,
    method_id: `${id}@1`,
    unit: 'count',
    value_num: '3',
    scope_type: 'run',
    scope_key: 'run',
    ...over,
  });

export const codeEntries = () => [
  entry(SECRETS, { group: 'code', unit: 'count' }),
  entry(DUP, { group: 'code', unit: 'count' }),
  entry(SUPP, { group: 'code', unit: 'count', level: 'A' }),
  entry('cost.gateway'),
];
