/** Wording for the findings opengrep stored; nothing here counts or filters by severity. */
import type { components } from '../../api/schema';

type FindingOut = components['schemas']['FindingOut'];

export const newFindings = (items: readonly FindingOut[], kind: 'security' | 'bug'): FindingOut[] =>
  items.filter((f) => f.state === 'new' && f.kind === kind);

export const findingText = (f: FindingOut): string =>
  `${f.rule} · ${f.path}:${f.line ?? '—'} · ${f.severity} · ${f.cwe.join(', ') || 'no CWE'}`;

export const findingsPath = (runId: string, analysisId: string): string =>
  `/runs/${runId}/analysis/${analysisId}/findings`;
