/** Reading a stored SARIF report: a link and one line per finding, nothing computed. */

export interface SarifFinding {
  rule: string;
  path: string;
  line: string;
  message: string;
}

const MISSING = '—';

export const sarifHref = (runId: string, analysisId: string, tool: string): string =>
  `/api/runs/${runId}/analysis/${analysisId}/sarif/${tool}`;

const asRecord = (value: unknown): Record<string, unknown> | null =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const text = (value: unknown): string =>
  typeof value === 'string' && value !== ''
    ? value
    : typeof value === 'number'
      ? `${value}`
      : MISSING;

export function sarifFindings(doc: unknown): SarifFinding[] {
  const runs = asRecord(doc)?.runs;
  if (!Array.isArray(runs)) return [];
  const found: SarifFinding[] = [];
  for (const run of runs) {
    const results = asRecord(run)?.results;
    if (!Array.isArray(results)) continue;
    for (const raw of results) {
      const result = asRecord(raw) ?? {};
      const locations = result.locations;
      const physical = asRecord(
        asRecord(Array.isArray(locations) ? locations[0] : null)?.physicalLocation,
      );
      found.push({
        rule: text(result.ruleId),
        path: text(asRecord(physical?.artifactLocation)?.uri),
        line: text(asRecord(physical?.region)?.startLine),
        message: text(asRecord(result.message)?.text),
      });
    }
  }
  return found;
}

export const findingLine = (f: SarifFinding): string => `${f.rule} · ${f.path}:${f.line}`;
