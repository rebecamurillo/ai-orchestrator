import type { components } from '../../src/api/schema';
import { entry } from './metrics-fixtures';
import { analysis, code } from './static-fixtures';

export type Entry = components['schemas']['CatalogueEntryOut'];

export const LINT = 'code.linter_warnings_new';
export const TYPECHECK = 'code.typecheck_errors_new';
export const COVERAGE = 'code.coverage_changed_lines';
export const EXECUTED = 'code.tests_executed';
export const F2P = 'code.fail_to_pass';
export const SECURITY = 'code.findings_security';
export const BUG = 'code.findings_bug';
export const FIRST = 'code.test_first_order';
export const HELDOUT = 'step.bench-v1.heldout_tests';

export const LIMITS = '1. no quality. 2. template compliance. 3. weakened tests.';

export const tierEntries = (): Entry[] =>
  [LINT, TYPECHECK, COVERAGE, EXECUTED, F2P, SECURITY, BUG].map((id) =>
    entry(id, { group: 'code', unit: 'count', level: 'A' }),
  );

export const firstEntry = (): Entry =>
  entry(FIRST, { group: 'code', unit: 'stories', level: 'A', limits: LIMITS });

export const stepEntry = (over: Partial<Entry> = {}): Entry =>
  entry(HELDOUT, {
    group: 'step',
    unit: 'tests',
    level: 'A',
    label: 'held-out tests',
    limits: 'only what the report holds',
    ...over,
  });

export const opengrepAnalysis = (over: Partial<ReturnType<typeof analysis>> = {}) =>
  analysis({
    analysis_id: 'an-app',
    repository_path: 'repos/app',
    sarif_tools: ['opengrep'],
    rule_pack_hash: 'abcdef1234567890',
    ...over,
  });

export const run = (id: string, source: string | null, num: string | null, over = {}) =>
  code(id, { source, value_num: num, ...over });

export const FINDING: components['schemas']['FindingOut'] = {
  kind: 'security',
  rule: 'r.xss',
  path: 'a.py',
  line: 4,
  severity: 'high',
  cwe: ['CWE-79'],
  state: 'new',
};
