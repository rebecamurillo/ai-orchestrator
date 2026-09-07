/**
 * Pure reads for the Runs screen's QUEUE section (4.16, SPEC CAP-16, FR-25, UX-DR14): the
 * section-head text, the row fields, the request path `RunsQueue.tsx` shows on a failed
 * fetch, and the "is anything currently running" question the shared `$poll` cadence needs
 * (`stores/poll.ts`'s own contract — `Board.tsx`/`RunDetail.tsx`'s precedent). Kept out of
 * the island and the table so both unit-test without a DOM (`web-client/AGENTS.md`).
 *
 * `waiting` reuses `board/format.ts::ageText` unchanged rather than a local duplicate —
 * `QueueItemOut.waiting_seconds` is already in seconds, the same unit that helper takes; the
 * table imports it directly rather than through a wrapper here.
 *
 * **The `project` cell is the Run's own id, not a name.** `QueueItemOut.run` is
 * `RunSummaryOut` (4.4/4.9's "minimal" read model, reused whole by 4.11's `GET /queue`,
 * that story's own Code Map): it carries `project: UUID`, never a name — the one read model
 * that does is `GET /runs/{id}/detail`'s own `header.meta.project` (4.12), a second endpoint
 * this screen must not read to fill in a name (SPEC's own "a screen reads one endpoint and
 * aggregates nothing", root `AGENTS.md` AD-8, and this story's own operating rule: "do not
 * add, widen, or reshape" `GET /queue`). `projectCell` states that id plainly rather than
 * inventing a join against a second endpoint.
 */
import type { components } from '../../api/schema';

export type QueueItemOut = components['schemas']['QueueItemOut'];
export type QueueOut = components['schemas']['QueueOut'];
export type QueueRun = QueueItemOut['run'];

/** The fixed reason `GET /queue` states for a parked (`needs_you`) Run — the one reason that
 * carries the extra hint line (binding rule: "a parked Run's row adds the hint `not queued
 * until then` under the reason"). Duplicated from `application/use_cases/queue.py`'s own
 * `REASON_WAITING_ANSWER` rather than imported — that module is backend-api's own, and this
 * is the same small-literal-duplication convention `board/format.ts::tokenSignal` documents
 * for a handful of words shared across the two components. */
export const REASON_WAITING_ANSWER = 'waiting for your answer';

/** The fixed reason a row that is actually executing carries — `application/use_cases/
 * queue.py`'s own `REASON_RUNNING`, duplicated the same way `REASON_WAITING_ANSWER` above
 * is. Named rather than left as an inline literal in `hasRunningRow` below, so the one other
 * fixed-reason string this module compares against follows the same convention. */
export const REASON_RUNNING = 'running';

/** The hint a parked row's `waiting because` cell adds underneath the reason (binding rule),
 * stated once here rather than inlined at each caller. */
export const PARKED_HINT = 'not queued until then';

/** `pos · project · workflow · next step · waiting because · waiting` (binding rule) — the
 * dense table's own fixed column order. */
export const QUEUE_COLUMNS = [
  'pos',
  'project',
  'workflow',
  'next step',
  'waiting because',
  'waiting',
] as const;

/** `QUEUE · concurrency {n} · one active run per repository · parked runs hold a slot`
 * (UX-DR14) — `n` is always read off the endpoint's own payload (`QueueOut.
 * max_active_runs`), never a hardcoded figure (this story's own operating rule: "MAX_ACTIVE_
 * RUNS ... read it from the endpoint's own payload if it is there rather than hardcoding a
 * number on screen"). */
export function queueSectionHeadText(maxActiveRuns: number): string {
  return (
    `QUEUE · concurrency ${maxActiveRuns} · one active run per repository · ` +
    'parked runs hold a slot'
  );
}

/** `pos` cell: the engine's own position, or an em dash for a Run that already holds its
 * slot — `running`, or parked at `needs_you` (AD-12: "the repository lock is the queue
 * partition, held for the Run's whole life including `needs_you`" — a parked Run is holding
 * a slot, not waiting for one). */
export function positionText(position: number | null): string {
  return position === null ? '—' : String(position);
}

/** `workflow` cell text: `{template} v{n} · {branch}` (binding rule), verbatim off the one
 * Run summary this row carries. */
export function workflowText(run: QueueRun): string {
  return `${run.template} v${run.version} · ${run.branch}`;
}

/** `/workflows/{id}` — the `workflow` cell's own link target, the same route `RunCard.tsx`
 * links a Board card to. */
export function workflowHref(run: QueueRun): string {
  return `/workflows/${run.id}`;
}

/** `project` cell: the Run's own `project` id, verbatim (this module's own doc — the
 * endpoint carries no name to join against). */
export function projectCell(run: QueueRun): string {
  return run.project;
}

/** `next step` cell: the engine's own label, or an em dash for the one edge case a Run with
 * no rows of its own yet would otherwise print as a blank cell. */
export function nextStepText(row: QueueItemOut): string {
  return row.next_step_label.length > 0 ? row.next_step_label : '—';
}

/** Whether this row's reason carries the parked hint (binding rule). */
export function isParked(row: QueueItemOut): boolean {
  return row.reason === REASON_WAITING_ANSWER;
}

/** The request path `RunsQueue.tsx` always calls, and the one `FailedFetch` shows on a
 * failed poll — computed rather than read off a `Response.url`, `board/format.ts::
 * boardRequestPath`'s own precedent, so a network failure (no `Response` at all) still has
 * one to show. `GET /queue` takes no query parameters (4.11's own router), so unlike that
 * precedent this path never varies. */
export function queueRequestPath(): string {
  return '/api/queue';
}

/** The shared `$poll` cadence question (`stores/poll.ts`'s own contract): whether any row is
 * the one Run actually executing right now — the same question `Board.tsx`'s own `counts.
 * running > 0` and `RunDetail.tsx`'s own `run.status === 'running'` each answer for their
 * own read model, answered here off this row's own `reason` (never `run.status` — a row can
 * be `queued`/`needs_you` yet still print a stale `run.status` field the reason has already
 * superseded; `reason` is the one fixed sentence this endpoint promises, `application/
 * use_cases/queue.py::_reason`'s own source of truth). */
export function hasRunningRow(items: QueueItemOut[]): boolean {
  return items.some((row) => row.reason === REASON_RUNNING);
}
