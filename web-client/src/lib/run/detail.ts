/**
 * Every pure derivation `RunDetail.tsx` (4.15, SPEC CAP-15, FR-23) renders from a
 * `RunDetailOut` — kept out of the island and its `src/components/run/*` so it unit-tests
 * without a DOM (`web-client/AGENTS.md`), the same split `src/lib/board/format.ts` documents
 * for 4.14.
 *
 * **No `plan-diff` endpoint.** The brief's own implementation notes ask for a
 * `GET /runs/{id}/plan-diff` this story would add; the dispatch that started this story
 * says plainly that every endpoint the screen consumes already exists and none may be
 * added, widened or reshaped. Nothing in the domain stores the stale file's old and new
 * text anywhere either (`application/steps/plan_check.py` reads both copies to compare them
 * and keeps neither) — there is no data a new endpoint could even be built to expose without
 * a further domain change, which is further still out of this story's reach. The
 * `plan_stale` stop body below shows the reason and the path `alert.reason` already carries
 * (byte-identical to the brief's own "the banner reads `plan stale: stories.yaml`" AC) and
 * omits the line-diff panel; see the story's Design Notes for the full account.
 *
 * **No `run.park_path` on the wire either.** `RunDetailSummaryOut` does not carry it (only
 * `application/use_cases/run_views.py`'s own domain-side `Run.park_path` does), so "the
 * current row" is found the same way the backend's own `gate_record` already answers it:
 * `park_run`/`_fail`/`_cancel` (`application/use_cases/writers.py`,
 * `apply_step_result.py::_fail`) each append one record naming the row's own `path` at the
 * moment the Run stopped. Reading the *last* record of the matching event back off
 * `gate_record[]` (append-only, `at`-ordered — `infrastructure/db/repositories/gate_records.
 * py::list_for_run`) is exactly that same fact, published.
 */
import type { components } from '../../api/schema';
import { ageText } from '../board/format';

export type RunDetailOut = components['schemas']['RunDetailOut'];
export type StepRowOut = components['schemas']['StepRowOut'];
export type GateRecordOut = components['schemas']['GateRecordOut'];
export type StoryCellOut = components['schemas']['StoryCellOut'];
export type CostOut = components['schemas']['CostOut'];
export type AlertOut = components['schemas']['AlertOut'];
export type AttributionOut = components['schemas']['AttributionOut'];
export type CheckpointStoryOut = components['schemas']['CheckpointStoryOut'];
export type ParkKind = NonNullable<AlertOut['park_kind']>;
export type SignalKind = RunDetailOut['admitted_signals'][number];
export type RunStatus = RunDetailOut['run']['status'];

export type Token = 'QUE' | 'RUN' | 'BLK' | 'CHK' | 'DON' | 'ERR' | 'CAN' | 'SKP';
export type Level = 'needs-you' | 'failed';

const LIFECYCLE_TOKENS: Record<Exclude<RunStatus, 'needs_you'>, Token> = {
  queued: 'QUE',
  running: 'RUN',
  done: 'DON',
  failed: 'ERR',
  cancelled: 'CAN',
};

/** The Run's own token (Consistency Conventions): `BLK`/`CHK` while parked, off the alert's
 * own `park_kind`, the fixed table otherwise — `application/use_cases/run_views.py::
 * _run_token`'s own rule, duplicated the way `RunCard.tsx` already duplicates `StatusToken.
 * astro`'s `SIGNALS` map (small, established local duplication across the API boundary). */
export function runToken(run: RunDetailOut['run'], alert: AlertOut | null): Token {
  if (run.status === 'needs_you') return alert?.park_kind === 'checkpoint' ? 'CHK' : 'BLK';
  return LIFECYCLE_TOKENS[run.status];
}

/** `needs-you` for `BLK`/`CHK`, `failed` for `ERR`, `null` for every other token — what the
 * banner's 2px left rule colours, and the only two Run states the Alert banner itself (as
 * opposed to the Other-states banner replacements) ever renders for. */
export function bannerLevel(token: Token): Level | null {
  if (token === 'BLK' || token === 'CHK') return 'needs-you';
  if (token === 'ERR') return 'failed';
  return null;
}

/** The most recent `gate_record[]` entry whose `event` is one of `events`, or `null` — read
 * back-to-front since the list arrives oldest first (see this module's own doc). */
function lastRecord(records: GateRecordOut[], events: readonly string[]): GateRecordOut | null {
  for (let i = records.length - 1; i >= 0; i -= 1) {
    if (events.includes(records[i]!.event)) return records[i]!;
  }
  return null;
}

/** The row `path` names, or `null`. */
export function stepAt(steps: StepRowOut[], path: string | null | undefined): StepRowOut | null {
  if (path == null) return null;
  return steps.find((step) => step.path === path) ?? null;
}

/** The row the Run is currently stopped on — the parked row while `needs_you` (matched by
 * `alert.park_kind` against the gate record `park_run` wrote), the failing row while
 * `failed` (matched by the `failed` record `apply_step_result.py::_fail` wrote), the running
 * row while `running`, and `null` otherwise (this module's own doc explains why no
 * `park_path` field is read directly). */
export function currentStepPath(detail: RunDetailOut): string | null {
  if (detail.run.status === 'needs_you' && detail.alert) {
    const record = lastRecord(detail.gate_record, [detail.alert.park_kind ?? '']);
    if (record?.path) return record.path;
  }
  if (detail.run.status === 'failed') {
    const record = lastRecord(detail.gate_record, ['failed']);
    if (record?.path) return record.path;
  }
  if (detail.run.status === 'running') {
    const running = detail.steps.find((step) => step.status === 'running');
    if (running) return running.path;
  }
  return null;
}

/** The banner's own text — `alert.reason` verbatim while parked, the `failed` gate record's
 * `text` while failed (no `alert` is published for a `failed` Run — see this module's own
 * doc), empty otherwise. */
export function bannerText(detail: RunDetailOut): string {
  if (detail.run.status === 'needs_you') return detail.alert?.reason ?? '';
  if (detail.run.status === 'failed') {
    return lastRecord(detail.gate_record, ['failed'])?.text ?? '';
  }
  return '';
}

/** `cancelled by operator at {time}` — the `cancel` gate record's own timestamp, the only
 * durable record of when a Run was cancelled (`Run` itself carries no such field). */
export function cancelledAtText(detail: RunDetailOut): string {
  const record = lastRecord(detail.gate_record, ['cancel']);
  return record ? `cancelled by operator at ${record.at}` : 'cancelled by operator';
}

/** The last 40 lines of the current row's latest attempt — already tailed to 40 server-side
 * (`application/use_cases/run_views.py::_latest_attempt`), `.slice` here only guards a stub
 * or a future caller that is not. */
export function logTail(detail: RunDetailOut): string[] {
  const step = stepAt(detail.steps, currentStepPath(detail));
  return (step?.latest?.log_tail ?? []).slice(-40);
}

/** `{progress} · {links} · skipped: {ids} · epics skipped: {ns}` — the `done` summary line
 * replacing the banner. `summary.skipped_epics` (6.5) is optional on the wire
 * (`_drop_default`-guarded, `api/schemas/run_views.py::SummaryOut`) so a fixture built before
 * this story, which carries no such field, still reads as "nothing skipped" rather than
 * throwing. */
export function summaryLine(detail: RunDetailOut): string {
  const summary = detail.summary;
  if (!summary) return '';
  const parts: string[] = [];
  if (summary.progress) {
    const p = summary.progress;
    if (p.epics_total !== null) parts.push(`${p.epics_done ?? 0}/${p.epics_total} epics`);
    parts.push(`${p.stories_done}/${p.stories_total} stories`);
  }
  parts.push(`${summary.links.length} link${summary.links.length === 1 ? '' : 's'}`);
  let line = parts.join(' · ');
  if (summary.skipped.length > 0) line += ` · skipped: ${summary.skipped.join(', ')}`;
  const skippedEpics = summary.skipped_epics ?? [];
  if (skippedEpics.length > 0) line += ` · epics skipped: ${skippedEpics.join(', ')}`;
  return line;
}

/** `$4.18 / $15.00` — a ratio, never a percentage or a bar (`KvTable.astro`'s own rule).
 * Returns `"tracked, no cap"` verbatim when `budget_usd` is null (story 3-2, FR-17, NFR-8). */
export function moneyRatio(cost: CostOut): string {
  if (cost.budget_usd == null) return 'tracked, no cap';
  return `$${cost.spent_usd} / $${cost.budget_usd}`;
}

/** `123 in / 456 out`. */
export function tokensText(cost: CostOut): string {
  return `${cost.tokens_in} in / ${cost.tokens_out} out`;
}

/** Wall-clock as a duration, `board/format.ts::ageText`'s own breakdown (this story's own
 * reuse of 4.14's formatter rather than a second one). */
export function wallClockText(cost: CostOut): string {
  return ageText(cost.wall_clock_seconds);
}

/** Active Operator time as `hh:mm:ss` (zero-padded). `active_seconds: 0` renders
 * `00:00:00` — the store never posts 0, so this only appears on Runs with no tracked
 * activity (8.2). */
export function activeTimeText(cost: CostOut): string {
  const total = cost.active_seconds;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((n) => String(n).padStart(2, '0')).join(':');
}

/** The three kinds this epic's signals have any effect for (SPEC Non-goals: "No answer,
 * skip, budget raise, accept, or terminal signals"; `signal_run` accepts and then refuses
 * every other kind with `"{kind} not available yet"`). A control for a kind with no effect
 * is never offered, even where `admitted_signals` itself carries it. */
const EFFECTIVE_KINDS: readonly SignalKind[] = ['cancel', 'retry', 'continue'];

export function hasEffect(kind: SignalKind): boolean {
  return (EFFECTIVE_KINDS as readonly string[]).includes(kind);
}

/** `admitted_signals`, narrowed to the kinds this epic's controls ever render — `cancel`
 * excluded, since it is always its own dedicated, always-present-while-admitted button
 * rather than one of the Stop body's own. */
export function stopSignals(admitted: readonly SignalKind[]): SignalKind[] {
  return admitted.filter((kind) => hasEffect(kind) && kind !== 'cancel');
}

/** Stories grouped by `epic_index`, in first-seen order — what `StoriesStrip` renders one
 * section per. */
export function storiesByEpic(stories: StoryCellOut[]): [number, StoryCellOut[]][] {
  const order: number[] = [];
  const groups = new Map<number, StoryCellOut[]>();
  for (const cell of stories) {
    if (!groups.has(cell.epic_index)) {
      groups.set(cell.epic_index, []);
      order.push(cell.epic_index);
    }
    groups.get(cell.epic_index)!.push(cell);
  }
  return order.map((index) => [index, groups.get(index)!]);
}

/** `n/m` done count for one epic's own cells. */
export function epicDoneCount(cells: StoryCellOut[]): string {
  const done = cells.filter((cell) => cell.state === 'done').length;
  return `${done}/${cells.length}`;
}

/** The Alert banner's own "right-aligned progress" (binding rule), reconstructed from
 * `stories[]` rather than read off a `progress` field — `RunDetailOut` carries one only
 * inside `summary`, which is `null` until the Run is `done` (`application/use_cases/
 * run_views.py::_summary`). `stories[]` is present at every status, so counting its own
 * cells' `state` answers the same question `_progress` does server-side, without a wider
 * endpoint: `stories_total`/`stories_done` from every cell, `epics_total`/`epics_done` from
 * `storiesByEpic`'s own groups, but only for `initiative` — an `epic` Run's Template has no
 * epic frame of its own, the same distinction `_progress` draws on `run.template_name`. `''`
 * for a Run with no Story frame at all (`repo-init`). */
export function storiesProgressText(detail: RunDetailOut): string {
  const stories = detail.stories;
  if (stories.length === 0) return '';
  const storiesDone = stories.filter((cell) => cell.state === 'done').length;
  if (detail.run.template !== 'initiative') {
    return `${storiesDone}/${stories.length} stories`;
  }
  const groups = storiesByEpic(stories);
  const epicsDone = groups.filter(([, cells]) =>
    cells.every((cell) => cell.state === 'done' || cell.state === 'skipped'),
  ).length;
  return `${epicsDone}/${groups.length} epics · ${storiesDone}/${stories.length} stories`;
}

/** `status · skipped — {reason}` for a skipped Step row, the token's own word otherwise —
 * the Steps table's status cell (binding rule: "skipped rows: `skipped · {reason}`"). */
export function stepStatusText(step: StepRowOut): string {
  if (step.status === 'skipped') return `SKP · skipped — ${step.reason ?? ''}`;
  return step.token;
}

/** The header meta line, unabridged (binding rule: "never truncated, wraps if needed").
 * Model slot inserted between harness and started_at — EXPERIENCE-v1.md delta 26 (2026-09-15). */
export function metaLine(detail: RunDetailOut): string {
  const meta = detail.header.meta;
  const harness = meta.harness ?? '—';
  const model = meta.model ?? '—';
  const started = meta.started_at ?? '—';
  const worktree = meta.worktree_path ?? '—';
  return (
    `${meta.project} · ${meta.repository} · ${meta.base_branch} · ${meta.folder} · ` +
    `${meta.template} v${meta.version} · ${harness} · ${model} · ${started} · ${worktree}`
  );
}

//: The gate-record event that opened each Run status — read the same way `currentStepPath`
//: reads a park kind's own record, so the header's "age of the current state" (UX-DR9) and
//: the current row agree on what "current" means.
const STATE_EVENT: Partial<Record<RunStatus, readonly string[]>> = {
  failed: ['failed'],
  cancelled: ['cancel'],
  done: ['done'],
  running: ['start'],
};

/** When the Run entered its current status — the matching gate record's own `at`, `alert.
 * park_kind`'s record while parked, `run.created_at` for a Run still `queued`. */
export function stateEnteredAt(detail: RunDetailOut): string {
  if (detail.run.status === 'needs_you' && detail.alert) {
    const record = lastRecord(detail.gate_record, [detail.alert.park_kind ?? '']);
    if (record) return record.at;
  }
  const events = STATE_EVENT[detail.run.status];
  if (events) {
    const record = lastRecord(detail.gate_record, events);
    if (record) return record.at;
  }
  return detail.run.created_at;
}

/** Seconds since the Run entered its current status, floored at zero (a clock skew between
 * the browser and the server must never read as a negative age). */
export function stateAgeSeconds(detail: RunDetailOut, nowMs: number): number {
  const entered = new Date(stateEnteredAt(detail)).getTime();
  return Math.max(0, (nowMs - entered) / 1000);
}

/** The branch link the COST & TRACE block shows beside the compare links — built off a
 * compare URL's own host and repository path (`.../compare/{base}...{branch}` becomes
 * `.../tree/{branch}`, the shape `git.push`'s own compare link takes, e.g. GitHub's), since
 * `RunDetailOut` carries no repository host URL of its own. `null` before any compare URL
 * exists — a Run's branch has nothing to link to until it has been pushed at least once. */
export function branchLinkHref(detail: RunDetailOut): string | null {
  const first = detail.run.compare_urls[0];
  if (!first) return null;
  const marker = '/compare/';
  const at = first.indexOf(marker);
  if (at < 0) return null;
  return `${first.slice(0, at)}/tree/${detail.run.branch}`;
}

/** The crumb (UX-DR9): `workflows / {branch}`. */
export function crumbText(detail: RunDetailOut): string {
  return `workflows / ${detail.run.branch}`;
}

/** Which stop body to render: the parked row's own `park_kind` while `BLK`/`CHK`, `'failed'`
 * for `ERR` (the brief's own "Other states" body — a log tail and nothing else), `null` for
 * every other token (no stop body at all). */
export function stopKind(detail: RunDetailOut, token: Token): ParkKind | 'failed' | null {
  if ((token === 'BLK' || token === 'CHK') && detail.alert) return detail.alert.park_kind;
  if (token === 'ERR') return 'failed';
  return null;
}

/** The request path `FailedFetch` shows and the one this island's `api.GET` call always
 * makes — computed rather than read off a `Response.url`, `board/format.ts::
 * boardRequestPath`'s own reason. */
export function detailRequestPath(runId: string): string {
  return `/api/runs/${runId}/detail`;
}

/** The Question block's own eyebrow (5.10, UX-DR9): `Agent · {harness} · {model} ·
 * {ended_at}`, `—` for a part the parked row's attempt never got far enough to record. */
export function questionEyebrow(attribution: AttributionOut | null | undefined): string {
  const harness = attribution?.harness ?? '—';
  const model = attribution?.model ?? '—';
  const endedAt = attribution?.ended_at ?? '—';
  return `Agent · ${harness} · ${model} · ${endedAt}`;
}

//: `rules/routing.py::AMBIGUOUS_STORY_FILE` is the only `misconfigured` condition that names
//: files, always as `ambiguous story file: {comma-separated names}`.
const AMBIGUOUS_PREFIX = 'ambiguous story file: ';

/** The file list a `misconfigured` condition names, or `[]` — every condition but the
 * ambiguous-file one names none (5.10, UX-DR10). */
export function misconfiguredFiles(reason: string | null | undefined): string[] {
  if (!reason || !reason.startsWith(AMBIGUOUS_PREFIX)) return [];
  return reason
    .slice(AMBIGUOUS_PREFIX.length)
    .split(',')
    .map((name) => name.trim())
    .filter((name) => name.length > 0);
}

//: The extra kinds a `blocked`/`misconfigured` stop's own button row offers (5.10, SPEC
//: CAP-10) — `retry` (admitted for `misconfigured` only) and the two skips. Kept apart from
//: `EFFECTIVE_KINDS`/`hasEffect` above: those stay the exact three kinds the frozen
//: `run-detail-lib.test.ts` asserts this epic gives every other park kind.
const BLOCKED_EXTRA_KINDS: readonly SignalKind[] = ['retry', 'skip_story', 'skip_epic'];

/** `admitted_signals`, narrowed to the kinds a `blocked`/`misconfigured` stop's own button
 * row renders — never `answer` (Epic 6), never `cancel` (`StopBody`'s own dedicated button,
 * `stopSignals`'s own precedent). */
export function blockedSignals(admitted: readonly SignalKind[]): SignalKind[] {
  return admitted.filter((kind) => BLOCKED_EXTRA_KINDS.includes(kind));
}
