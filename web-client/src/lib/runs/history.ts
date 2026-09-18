/**
 * Pure reads for the Runs screen's HISTORY section (7.5, SPEC CAP-5, FR-25 history,
 * UX-DR14): the ten column heads, the text of each cell, the link a row carries, the request
 * path the island shows on a failed fetch, and the query it asks with. Kept out of the island
 * and the table so both unit-test without a DOM (`web-client/AGENTS.md`; `vitest.config.ts`
 * runs in `environment: 'node'`).
 *
 * **This table prints the path, never the label** (UX-DR16): it is a detail context that
 * never truncates, so `epics[0].stories[3].build` is what the `path` cell reads. The `time`
 * columns are two different facts and both are called `time` on screen because UX-DR14 names
 * them that way — the first is when the attempt started, the second is how long it took.
 *
 * **The token is the only coloured cell** (NFR-6, binding rule). `tokenSignal` is
 * `board/format.ts`'s own three-hue map, reused rather than restated so a card, a step row
 * and a history row never disagree about what a token means. `SKP` maps to `neutral` there,
 * which is what keeps a skipped attempt a plain word rather than a green one.
 *
 * **Nothing here derives a status** (AD-8). `status` and `token` are both read off the row
 * the endpoint sent; this module chooses no token and reclassifies no attempt.
 */
import type { components } from '../../api/schema';
import { encode } from '../step-path';

export type HistoryRowOut = components['schemas']['HistoryRowOut'];
export type HistoryPageOut = components['schemas']['HistoryPageOut'];

/** `time · project · workflow · path · kind · harness · status · time · cost · trace`
 * (UX-DR14) — the dense table's own fixed column order, ten of them. */
export const HISTORY_COLUMNS = [
  'time',
  'project',
  'workflow',
  'path',
  'kind',
  'harness',
  'status',
  'time',
  'cost',
  'trace',
] as const;

/** The status tokens the Runs bar offers (UX-DR14). `ALL` is the absence of a filter and is
 * never sent to the endpoint; the other five are `application/use_cases/history.py::
 * STATUS_FILTERS`'s own keys, duplicated the same way `runs/queue.ts` duplicates that
 * endpoint's fixed reasons — a handful of tokens shared across the two components. */
export const HISTORY_STATUS_TOKENS = ['QUE', 'RUN', 'BLK', 'ERR', 'DON'] as const;

/** The em dash a cell prints when the row carries no value for it — a non-agent attempt's
 * harness, an attempt still running, a Run with no trace. One character, stated once. */
export const EMPTY_CELL = '—';

/** The `trace` cell's own text when the row has a link; the link target is `trace_url`. */
export const TRACE_LINK_TEXT = 'trace';

/** The control that loads the next page, and the reading that replaces it at the end. */
export const MORE_LABEL = 'more';
export const END_TEXT = 'no more attempts';

/** The reading the section shows when nothing has ever executed under these filters. */
export const HISTORY_EMPTY_HEADLINE = 'NO ATTEMPTS';
export const HISTORY_EMPTY_LINE = 'nothing has executed yet.';

/** `HISTORY` (binding rule) — the section head, the word and nothing after it. */
export const HISTORY_SECTION_HEAD = 'HISTORY';

/** The clock reading of the first `time` column: when this attempt started. Local-independent
 * — the payload is ISO 8601 UTC ending in `Z` and this prints its `HH:MM:SS`, the same way
 * `board/format.ts::clockText` reads a Board card's own timestamp. */
export function startedText(row: HistoryRowOut): string {
  return row.started_at.slice(11, 19);
}

/** The second `time` column: how long the attempt took, or the em dash while it is running.
 * Whole seconds — a history row compares harnesses, and a millisecond is not that comparison. */
export function durationText(row: HistoryRowOut): string {
  return row.seconds == null ? EMPTY_CELL : `${Math.round(row.seconds)}s`;
}

/** `cost` cell: the decimal string the endpoint sent, prefixed, with `provisional` after it
 * while the figure is still the harness's own estimate rather than LiteLLM's settled spend
 * (5.10). A local model records `0.000000` with real tokens beside it (PRD §11), which is a
 * cost of zero and not an absent one — so only a `null` reads as the em dash. */
export function costText(row: HistoryRowOut): string {
  if (row.cost_usd == null) return EMPTY_CELL;
  return `$${row.cost_usd}${row.cost_provisional ? ' provisional' : ''}`;
}

/** `harness` cell: the harness and the model it ran, or the em dash on a non-agent row. */
export function harnessText(row: HistoryRowOut): string {
  if (!row.harness) return EMPTY_CELL;
  return row.model ? `${row.harness} · ${row.model}` : row.harness;
}

/** `workflow` cell: `{template} v{n} · {branch}`, verbatim off the row. */
export function workflowText(row: HistoryRowOut): string {
  return row.run_label;
}

/** Where a row links: the Run detail, scrolled to this row (binding rule). The fragment is
 * the row's `seq`, which is why `HistoryRowOut` carries one. */
export function rowHref(row: HistoryRowOut): string {
  return `/workflows/${row.run_id}#step-${row.seq}`;
}

/** Where a history row links when the step-run detail page is available (story 1-2).
 * The path segment uses dot-index encoding so URL brackets are avoided.
 * `rowHref` is left unchanged (frozen assertion at `runs-history-lib.test.ts:127`). */
export function stepDetailHref(row: HistoryRowOut): string {
  return `/workflows/${row.run_id}/steps/${encode(row.path)}`;
}

/** The query `GET /steps` is asked with. `ALL` and a missing project are omitted rather than
 * sent empty, so the request path a failed fetch names is the request that was made. */
export function historyQuery(
  projectId: string | null,
  status: string | null,
  cursor: string | null,
): Record<string, string> {
  const query: Record<string, string> = {};
  if (projectId) query.project_id = projectId;
  if (status && status !== 'ALL') query.status = status;
  if (cursor) query.cursor = cursor;
  return query;
}

/** The request path the island shows on a failed fetch — computed rather than read off a
 * `Response.url`, `board/format.ts::boardRequestPath`'s own precedent, so a network failure
 * with no `Response` at all still has one to show. */
export function historyRequestPath(
  projectId: string | null,
  status: string | null,
  cursor: string | null = null,
): string {
  const query = historyQuery(projectId, status, cursor);
  const parts = Object.entries(query).map(([key, value]) => `${key}=${encodeURIComponent(value)}`);
  return parts.length > 0 ? `/api/steps?${parts.join('&')}` : '/api/steps';
}

/** A row of an attempt still executing: UX-DR14 promotes the current rows. Read, not derived
 * — this is the row's own stored status (AD-8). */
export function isCurrent(row: HistoryRowOut): boolean {
  return row.status === 'running';
}

/** Newest first, current rows promoted (UX-DR14): the running attempts keep the order the
 * endpoint gave them and sit above the rest, which keep theirs. A stable partition rather
 * than a sort, so nothing else about the endpoint's own `started_at desc, id desc` moves. */
export function promoted(rows: HistoryRowOut[]): HistoryRowOut[] {
  return [...rows.filter(isCurrent), ...rows.filter((row) => !isCurrent(row))];
}
