/**
 * The redirect `src/pages/templates/index.astro` performs (3.5, AC1): bare `/templates`
 * opens on the latest version of the first Template, ordered by name. Kept as a pure
 * function, with no fetch of its own, so the ordering rule is unit-tested with no server and
 * no browser — the page only supplies the list it already read from `GET /api/v1/templates`.
 */
import type { components } from '../../api/schema';

export type TemplateSummary = components['schemas']['TemplateSummaryOut'];

export interface RedirectTarget {
  name: string;
  version: number;
}

/**
 * `null` for an empty list — the page renders the empty state instead of redirecting.
 * Names are unique, so a plain `localeCompare` sort is enough to find "the first by name";
 * the input array is never mutated.
 */
export function selectRedirectTarget(items: TemplateSummary[]): RedirectTarget | null {
  if (items.length === 0) return null;

  const first = [...items].sort((a, b) => a.name.localeCompare(b.name))[0]!;
  return { name: first.name, version: first.latest_version };
}
