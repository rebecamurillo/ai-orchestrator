/**
 * Every derived wording of the metric primitives (EXPERIENCE §4) is built here; components
 * only place these strings. Catalogue text (labels, methods, sources) is never built here.
 */
import type { components } from '../../api/schema';
import type { OriginTarget } from '../../stores/metric-ui';

type MetricValueOut = components['schemas']['MetricValueOut'];
type ResultVersionOut = components['schemas']['ResultVersionOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

export type Spans = NonNullable<OriginTarget['spans']>;
export type OriginRow = readonly [key: string, text: string, copy: boolean];

const GROUPED = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

export function formatValue(valueNum: string, unit: string): string {
  const n = Number(valueNum);
  switch (unit) {
    case 'USD':
      return `$${n.toFixed(2)}`;
    case 'seconds': {
      const minutes = Math.floor(n / 60);
      return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`;
    }
    case 'ratio':
      return n.toFixed(2);
    case '%':
      return `${n.toFixed(2)} %`;
    default:
      return GROUPED.format(n);
  }
}

export const LIST_PRICE_WORDS = 'list-price equivalent';
export const NOT_AVAILABLE_WORD = 'not available';

export function partialWord(
  value: Pick<MetricValueOut, 'metric_id' | 'partial_n' | 'partial_m'>,
): string | null {
  if (value.partial_n === null || value.partial_m === null) return null;
  const noun = value.metric_id.startsWith('code.') ? 'repositories' : 'attempts';
  return `partial · ${value.partial_n} of ${value.partial_m} ${noun}`;
}

export function stateWords(value: MetricValueOut, subscription: boolean): string[] {
  const words: string[] = [];
  if (subscription && value.unit === 'USD') words.push(LIST_PRICE_WORDS);
  const partial = partialWord(value);
  if (partial !== null) words.push(partial);
  if (value.carried_from !== null) words.push(`from v${value.carried_from}`);
  return words;
}

export function entryPointWords(points: readonly string[]): string {
  return points.map((p) => p.replaceAll('_', ' ')).join(' + ');
}

export function calculatedAt(iso: string): string {
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)}Z`;
}

const SPAN_NOUNS: Record<string, [key: keyof Spans, many: string, none: string]> = {
  spans_models: ['models', 'models', 'more than one model'],
  spans_repositories: ['repositories', 'repositories', 'more than one repository'],
  spans_harnesses: ['harnesses', 'harnesses', 'more than one harness'],
};

const FIXED_NA: Record<string, string> = {
  no_model_called: 'no model called',
  no_repository_scope: 'the value has no repository scope',
  no_repository_record: 'no repository record',
  commit_missing: 'commit missing',
};

export function naWords(reason: string, scopeType: string, spans?: Spans): string {
  const span = SPAN_NOUNS[reason];
  if (span) {
    const [key, many, none] = span;
    const count = spans?.[key];
    if (count === undefined) return none;
    return `${scopeType === 'run' ? 'a Run total' : `the ${scopeType}`} spans ${count} ${many}`;
  }
  return FIXED_NA[reason] ?? reason.replaceAll('_', ' ');
}

export function countSpans(items: readonly MetricValueOut[]): Spans {
  const distinct = (pick: (v: MetricValueOut) => string | null) =>
    new Set(items.map(pick).filter((x): x is string => x !== null)).size;
  return { models: distinct((v) => v.model), repositories: distinct((v) => v.repository) };
}

export function originRows(target: OriginTarget, entry: CatalogueEntryOut): OriginRow[] {
  const { value, version, latest, spans } = target;
  const origin = value.origin;
  const noVersion = 'n/a — no result version';
  const noOrigin = 'n/a — no origin recorded';
  const field = (text: string | null, reason: string | null): string =>
    text ?? `n/a — ${naWords(reason ?? 'unknown', value.scope_type, spans)}`;
  const fromOrigin = (pick: (o: NonNullable<typeof origin>) => string): string =>
    origin ? pick(origin) : noOrigin;
  // a copy control copies an id, a branch or a commit — never a name or an `n/a` line
  const copyable = (raw: string | null | undefined): boolean =>
    origin !== null && raw !== null && raw !== undefined;

  return [
    ['metric', `${entry.id} · ${entry.label}`, false],
    ['method', value.method_id, false],
    ['calculated', version ? calculatedAt(version.calculated_at) : noVersion, false],
    ['entry point', version ? entryPointWords(version.entry_point) : noVersion, false],
    [
      'result version',
      version ? `v${version.n}${version.n === latest ? ' (latest)' : ''}` : noVersion,
      false,
    ],
    [
      'project',
      target.projectName ?? fromOrigin((o) => o.project_id),
      target.projectName === undefined && copyable(origin?.project_id),
    ],
    ['Run', fromOrigin((o) => o.run_id), copyable(origin?.run_id)],
    ['template', fromOrigin((o) => `${o.template_name}@${o.template_version}`), false],
    ['harness', fromOrigin((o) => field(o.harness, o.harness_na)), false],
    ['model', fromOrigin((o) => field(o.origin_model, o.origin_model_na)), false],
    ['repository', fromOrigin((o) => field(o.origin_repository, o.origin_repository_na)), false],
    ['branch', fromOrigin((o) => field(o.branch, o.branch_na)), copyable(origin?.branch)],
    ['commit', fromOrigin((o) => field(o.commit, o.commit_na)), copyable(origin?.commit)],
    [
      'base commit',
      fromOrigin((o) => field(o.base_commit, o.base_commit_na)),
      copyable(origin?.base_commit),
    ],
  ];
}

export interface VersionView {
  segments: number[];
  overflow: boolean;
  latest: number | null;
  detail: string;
}

export function versionView(versions: readonly ResultVersionOut[], selected: number): VersionView {
  const ns = versions.map((v) => v.n).sort((a, b) => a - b);
  const overflow = ns.length > 5;
  const chosen = versions.find((v) => v.n === selected);
  const parts = chosen
    ? [
        `calculated ${calculatedAt(chosen.calculated_at)}`,
        entryPointWords(chosen.entry_point),
        ...(chosen.methods_changed.length > 0
          ? [`methods changed: ${chosen.methods_changed.join(', ')}`]
          : []),
      ]
    : [];
  return {
    segments: overflow ? ns.slice(-4) : ns,
    overflow,
    latest: ns.length > 0 ? ns[ns.length - 1]! : null,
    detail: parts.join(' · '),
  };
}
