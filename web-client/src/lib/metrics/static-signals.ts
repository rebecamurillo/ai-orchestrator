/**
 * Wording and shaping for STATIC SIGNALS ON THE CHANGE (Run page and comparison). Every figure
 * is a stored `metric_value` or a stored analysis field, printed as given; what is derived here
 * is layout: tier membership, scope order, the raw/rate split and the tool-version flag.
 */
import type { components } from '../../api/schema';
import { formatValue } from './format';

type AnalysisOut = components['schemas']['AnalysisOut'];
type MetricValueOut = components['schemas']['MetricValueOut'];
type CompareMetricOut = components['schemas']['CompareMetricOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

export const STATIC_HEAD = 'STATIC SIGNALS ON THE CHANGE';
export const STATIC_SUB = 'findings are possible, leads to review · no single score';
export const TIER_1A = 'TIER 1A · OFFLINE';
export const TIER_2 = 'TIER 2 · OPT-IN';
export const TIER_3 = 'TIER 3 · FROM WORKFLOW STEPS';
export const NA_WORD = 'n/a';
export const RUN_SCOPE = 'all repositories';
export const RAW_HEAD = 'raw';
export const RATE_HEAD = 'per 100 prod. lines';
export const TOOLS_DIFFER = '≠ tool versions differ';
export const SMALL_CHANGE = 'small change';
const NOT_RUN = 'not run';

export const tier1bHead = (date: string | null): string => `TIER 1B · LOOKUPS ${date ?? NOT_RUN}`;

export const notRunLine = (n: number): string => `not run in v${n} · RECALCULATE METRICS runs it`;

export const TIER_1B_IDS: readonly string[] = [
  'code.deps_changed',
  'code.deps_not_in_registry',
  'code.deps_known_vulns',
  'code.deps_recent',
  'code.deps_licences',
  'code.duplication_added',
  'code.functions_over_cyclomatic',
  'code.functions_over_cognitive',
];

export const TIER_2_IDS: readonly string[] = [
  'code.linter_warnings_new',
  'code.typecheck_errors_new',
  'code.coverage_changed_lines',
  'code.tests_executed',
  'code.fail_to_pass',
  'code.findings_security',
  'code.findings_bug',
];

export const TEST_FIRST = 'code.test_first_order';
export const FINDING_IDS: Readonly<Record<string, 'security' | 'bug'>> = {
  'code.findings_security': 'security',
  'code.findings_bug': 'bug',
};
export const SEVERITIES = ['high', 'medium', 'low'] as const;

export const FINDING_TOOLS: Readonly<Record<string, string>> = {
  'code.findings_security': 'opengrep',
  'code.findings_bug': 'opengrep',
  'code.possible_secrets': 'gitleaks',
  'code.deps_known_vulns': 'osv-scanner',
  'code.duplication_added': 'jscpd',
};

const TOOL_ORDER = ['gitleaks', 'jscpd', 'lizard', 'osv-scanner'];

export type StaticCell = Pick<
  MetricValueOut,
  'source' | 'value_num' | 'missing' | 'unit' | 'scope_type' | 'scope_key'
>;

const isRate = (source: string | null): boolean =>
  source !== null && (source === 'per_100' || source.endsWith(':per_100'));

export function splitCells<T extends Pick<StaticCell, 'source'>>(
  cells: readonly T[],
): { raws: T[]; rates: T[]; small: T[] } {
  const raws: T[] = [];
  const rates: T[] = [];
  const small: T[] = [];
  for (const cell of cells) {
    if (cell.source === 'small_change') small.push(cell);
    else if (isRate(cell.source)) rates.push(cell);
    else raws.push(cell);
  }
  return { raws, rates, small };
}

export const sourceWord = (source: string | null): string | null =>
  source === null ? null : source.replace(/[_:]/g, ' ');

/** The words a labelled cell carries: a severity reads `possible {severity}` after the figure. */
export function cellWords(
  metricId: string,
  source: string | null,
): { before: string | null; after: string | null } {
  const severity = (SEVERITIES as readonly (string | null)[]).includes(source);
  if (metricId in FINDING_IDS && severity) return { before: null, after: `possible ${source}` };
  return { before: sourceWord(source), after: null };
}

export function testFirstLine(readable: string | null, stories: string | null): string {
  const head = 'test-first order · method followed, not quality';
  if (readable === null || stories === null) return head;
  return (
    `${head} · ${formatValue(readable, 'stories')} of ${formatValue(stories, 'stories')} ` +
    'stories readable from the logs'
  );
}

const short = (sha: string | null): string => (sha === null ? '—' : sha.slice(0, 7));

export function detailLine(a: AnalysisOut): string {
  if (a.status === 'failed') return a.reason;
  const outside =
    a.commits_outside_run === null
      ? 'commits outside this Run not recorded'
      : a.commits_outside_run === 0
        ? 'head holds no commits outside this Run'
        : `head holds ${a.commits_outside_run} commit${a.commits_outside_run === 1 ? '' : 's'} this Run did not make`;
  const languages = a.languages === null ? 'languages not recorded' : a.languages.join(', ');
  return (
    `${languages} · base ${short(a.base)} (merge base with ${a.base_branch ?? '—'}) → ` +
    `head ${short(a.head)} · ${outside}`
  );
}

function versionsByTool(analyses: readonly AnalysisOut[]): Map<string, string[]> {
  const found = new Map<string, string[]>();
  for (const a of analyses) {
    for (const t of a.tools) {
      const held = found.get(t.tool) ?? [];
      if (!held.includes(t.version)) held.push(t.version);
      found.set(t.tool, held);
    }
  }
  return found;
}

const datesOf = (values: readonly (string | null)[]): string => {
  const present = [...new Set(values.filter((d): d is string => d !== null))];
  return present.length === 0 ? NOT_RUN : present.join(', ');
};

export function lookupDate(analyses: readonly AnalysisOut[]): string | null {
  const dates = analyses.map((a) => a.lookup_date).filter((d): d is string => d !== null);
  return dates.length === 0 ? null : [...new Set(dates)].join(', ');
}

export function footerLines(analyses: readonly AnalysisOut[]): string[] {
  const versions = versionsByTool(analyses);
  const tools = [...versions.keys()].sort(
    (a, b) =>
      (TOOL_ORDER.indexOf(a) === -1 ? 99 : TOOL_ORDER.indexOf(a)) -
      (TOOL_ORDER.indexOf(b) === -1 ? 99 : TOOL_ORDER.indexOf(b)),
  );
  const hashes = [...new Set(analyses.map((a) => a.declaration_hash?.slice(0, 8) ?? 'absent'))];
  const packs = [
    ...new Set(analyses.flatMap((a) => (a.rule_pack_hash ? [a.rule_pack_hash.slice(0, 8)] : []))),
  ];
  return [
    `tools: ${tools.map((t) => `${t} ${(versions.get(t) ?? []).join('/')}`).join(' · ')}`,
    packs.length > 0
      ? `rule packs: opengrep ${packs.join('/')}`
      : 'rule packs: n/a — Tier 1 runs no rule pack',
    `vulnerability database ${datesOf(analyses.map((a) => a.vulnerability_db_date))}`,
    `registry lookup ${datesOf(analyses.map((a) => a.lookup_date))}`,
    `declaration orchestrator-analysis.yaml ${hashes.join('/')}`,
  ];
}

export interface StaticRow {
  metricId: string;
  cells: StaticCell[];
}
export interface StaticScope {
  key: string;
  name: string;
  detail: string | null;
  analysis: AnalysisOut | null;
  rows: StaticRow[];
}
export interface StaticTier {
  tier: '1a' | '1b' | '2';
  head: string;
  scopes: StaticScope[];
}

export function staticTable(
  items: readonly MetricValueOut[],
  analyses: readonly AnalysisOut[],
  entries: Readonly<Record<string, CatalogueEntryOut>>,
  set: 'headline' | 'all',
): StaticTier[] {
  const code = Object.values(entries).filter(
    (e) => e.group === 'code' && (set === 'all' || e.level === 'H'),
  );
  const date = lookupDate(analyses);
  const scopes: { key: string; type: string; name: string; analysis: AnalysisOut | null }[] = [
    { key: 'run', type: 'run', name: RUN_SCOPE, analysis: null },
    ...analyses.map((a) => ({
      key: a.repository_path,
      type: 'repository',
      name: a.repository_path,
      analysis: a,
    })),
  ];
  const heads = { '1a': TIER_1A, '1b': tier1bHead(date), '2': TIER_2 } as const;
  const inTier = (e: CatalogueEntryOut, tier: StaticTier['tier']): boolean => {
    if (tier === '2') return TIER_2_IDS.includes(e.id);
    if (TIER_2_IDS.includes(e.id) || e.id === TEST_FIRST) return false;
    return TIER_1B_IDS.includes(e.id) === (tier === '1b');
  };
  return (['1a', '1b', '2'] as const).map((tier) => ({
    tier,
    head: heads[tier],
    scopes: scopes.map((scope) => ({
      key: scope.key,
      name: scope.name,
      analysis: scope.analysis,
      detail: scope.analysis === null ? null : detailLine(scope.analysis),
      rows: code
        .filter((e) => inTier(e, tier))
        .sort((a, b) => (tier === '2' ? TIER_2_IDS.indexOf(a.id) - TIER_2_IDS.indexOf(b.id) : 0))
        .map((e) => ({
          metricId: e.id,
          cells: items.filter(
            (v) => v.metric_id === e.id && v.scope_type === scope.type && v.scope_key === scope.key,
          ),
        })),
    })),
  }));
}

export const isEmptyTier = (tier: StaticTier): boolean =>
  tier.scopes.every((scope) => scope.rows.every((row) => row.cells.length === 0));

export const hasAnalysisCode = (items: readonly MetricValueOut[]): boolean =>
  items.some((v) => v.metric_id.startsWith('code.') && v.metric_id !== TEST_FIRST);

export interface TierThree {
  testFirst: StaticCell[] | null;
  steps: { metricId: string; cells: StaticCell[] }[];
}

const COUNT_SOURCES = ['readable', 'stories'];

/** Run scope only: the test-first outcomes, then one entry per step-produced metric. */
export function tierThree(
  items: readonly MetricValueOut[],
  stepEntries: readonly CatalogueEntryOut[],
  set: 'headline' | 'all',
): TierThree {
  const atRun = (id: string) =>
    items.filter((v) => v.metric_id === id && v.scope_type === 'run' && v.scope_key === 'run');
  const first = atRun(TEST_FIRST);
  return {
    testFirst:
      first.length === 0 ? null : first.filter((v) => !COUNT_SOURCES.includes(v.source ?? '')),
    steps: stepEntries
      .filter((e) => set === 'all' || e.level === 'H')
      .map((e) => ({ metricId: e.id, cells: atRun(e.id) })),
  };
}

/** Per tool, the version of each Run that has a toolset, in the order the Runs are shown. */
function differing(
  metric: CompareMetricOut,
  order: readonly string[],
): { tool: string; groups: { version: string; runs: number[] }[] }[] {
  const tools = new Set<string>();
  for (const list of Object.values(metric.toolsets)) for (const t of list) tools.add(t.tool);
  const found: ReturnType<typeof differing> = [];
  for (const tool of [...tools].sort()) {
    const groups: { version: string; runs: number[] }[] = [];
    order.forEach((runId, at) => {
      const version = metric.toolsets[runId]?.find((t) => t.tool === tool)?.version;
      if (version === undefined) return;
      const group = groups.find((g) => g.version === version);
      if (group) group.runs.push(at + 1);
      else groups.push({ version, runs: [at + 1] });
    });
    if (groups.length > 1) found.push({ tool, groups });
  }
  return found;
}

export function toolFlag(
  metric: CompareMetricOut,
  runs: readonly { run_id: string }[],
): string | null {
  if (!metric.tool_versions_differ) return null;
  const named = differing(
    metric,
    runs.map((r) => r.run_id),
  ).map(({ tool, groups }) => {
    const parts = groups.map(
      (g) => `${g.version} (${g.runs.length === 1 ? 'Run' : 'Runs'} ${g.runs.join(', ')})`,
    );
    return `${tool} ${parts.join(' vs ')}`;
  });
  return `${TOOLS_DIFFER}: ${named.join('; ')}`;
}

export function toolLine(metric: CompareMetricOut, runId: string): string | null {
  if (!metric.tool_versions_differ) return null;
  const mine = differing(metric, Object.keys(metric.toolsets))
    .map(({ tool }) => metric.toolsets[runId]?.find((t) => t.tool === tool))
    .filter((t) => t !== undefined)
    .map((t) => `${t.tool} ${t.version}`);
  return mine.length === 0 ? null : mine.join(' · ');
}
