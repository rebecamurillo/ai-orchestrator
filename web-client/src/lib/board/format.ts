/**
 * Every pure computation the Board renders from a `BoardOut` (SPEC CAP-14, FR-22): age text,
 * the aged-signal rule, the progress segment, the two readouts, the `done`/`failed` bound,
 * and the failed-fetch command line. Kept out of `Board.tsx` so it unit-tests without a DOM
 * (`web-client/AGENTS.md`) — the island only calls these and renders what they return.
 */
import type { components } from '../../api/schema';

export type CardOut = components['schemas']['CardOut'];
export type ProgressOut = components['schemas']['ProgressOut'];
export type BoardOut = components['schemas']['BoardOut'];

const MINUTE_S = 60;
const HOUR_S = 60 * MINUTE_S;
const DAY_S = 24 * HOUR_S;

/** The one tolerated pair (UX-DR2): a `BLK`/`CHK` card older than this has both its token
 * and its age amber. */
const AGED_THRESHOLD_S = 48 * HOUR_S;

/** `"2d 04h"`, `"3h 07m"`, `"12m"` — mirrors `src/lib/projects/runs.ts::ageText`'s own
 * breakdown, but from a card's `age_seconds` directly rather than an ISO `created_at` and a
 * `Date` (this codebase's established local-duplication convention for a handful of lines —
 * 4.12's Code Map documents the same choice for `_token`/`_TOKENS`). */
export function ageText(seconds: number): string {
  const elapsed = Math.max(0, seconds);
  if (elapsed >= DAY_S) {
    const days = Math.floor(elapsed / DAY_S);
    const hours = Math.floor((elapsed % DAY_S) / HOUR_S);
    return `${days}d ${String(hours).padStart(2, '0')}h`;
  }
  if (elapsed >= HOUR_S) {
    const hours = Math.floor(elapsed / HOUR_S);
    const minutes = Math.floor((elapsed % HOUR_S) / MINUTE_S);
    return `${hours}h ${String(minutes).padStart(2, '0')}m`;
  }
  return `${Math.floor(elapsed / MINUTE_S)}m`;
}

/** Whether this card's token and age both carry the amber signal (the binding rule's "an
 * age > 48h on a BLK/CHK card renders in amber"). */
export function isAgedNeedsYou(token: string, ageSeconds: number): boolean {
  return (token === 'BLK' || token === 'CHK') && ageSeconds > AGED_THRESHOLD_S;
}

export type Signal = 'run' | 'needs-you' | 'failed' | 'neutral';

/** `StatusToken.astro`'s own `SIGNALS` map, duplicated rather than imported: `RunCard.tsx`
 * cannot import a `.astro` component (React and Astro components are never mixed across that
 * boundary in this codebase), and this is the whole mapping, not a derivation of it, so
 * duplicating it here is the same "small local duplication" convention 4.12's Code Map
 * documents for `_token`/`_TOKENS`. Both copies are three-hue, so a change to one is a
 * change a reviewer can see needs the other. */
export function tokenSignal(token: string): Signal {
  if (token === 'RUN') return 'run';
  if (token === 'BLK' || token === 'CHK') return 'needs-you';
  if (token === 'ERR') return 'failed';
  return 'neutral';
}

/** The 2px left rule (binding rule: "A BLK/ERR card carries the 2px left rule in its signal
 * colour") — narrower than `tokenSignal` above: `CHK` gets the amber chip+token but not the
 * left rule, a deliberate per-card narrowing this story's brief states explicitly (Design
 * Notes). */
export function hasLeftRule(token: string): boolean {
  return token === 'BLK' || token === 'ERR';
}

/** The card's fixed-order progress segment: `n/n epics · m/m stories · k links`, the epics
 * clause omitted when `epics_total` is null (a plan with no epic frame has none); `kindLabel`
 * stands in
 * whole when `progress` itself is null — a plan with no Story frame, whose Template name the
 * server sends in its place. */
export function progressText(progress: ProgressOut | null, kindLabel: string | null): string {
  if (progress === null) return kindLabel ?? '';
  const parts: string[] = [];
  if (progress.epics_total !== null) {
    parts.push(`${progress.epics_done ?? 0}/${progress.epics_total} epics`);
  }
  parts.push(`${progress.stories_done}/${progress.stories_total} stories`);
  parts.push(`${progress.links} link${progress.links === 1 ? '' : 's'}`);
  return parts.join(' · ');
}

/** The oldest wait across the two columns that are waiting on something — `queued` (the
 * repository lock) and `needs_you` (the Operator). `running`/`done`/`failed` Runs are not
 * waiting. `null` when neither column holds a card, so the bar prints an em dash rather than
 * a false `0m`. */
export function oldestWaitSeconds(cards: CardOut[]): number | null {
  const waiting = cards.filter((card) => card.status === 'queued' || card.status === 'needs_you');
  if (waiting.length === 0) return null;
  return Math.max(...waiting.map((card) => card.age_seconds));
}

/** The footer readout (UX-DR3), byte-identical in shape to `FooterReadout.astro`'s own
 * `readout` template — `Board.tsx` patches the rendered element's text with this string
 * rather than reusing the component (see its own module doc for why). */
export function footerReadoutText(
  counts: { running: number; queued: number; needsYou: number },
  updated: string,
): string {
  return (
    `${counts.running} running · ${counts.queued} queued / ` +
    `${counts.needsYou} need you / updated ${updated}`
  );
}

/** The bar readout: `{n} runs · {k} need you · oldest wait {age}`. */
export function surfaceReadoutText(
  totalRuns: number,
  needsYou: number,
  oldestWait: number | null,
): string {
  const runsWord = `${totalRuns} run${totalRuns === 1 ? '' : 's'}`;
  const waitWord = oldestWait === null ? '—' : ageText(oldestWait);
  return `${runsWord} · ${needsYou} need you · oldest wait ${waitWord}`;
}

/** `hh:mm:ss` from an ISO instant, in the browser's own local clock — what `generated_at`
 * becomes for the footer's `updated` field. */
export function clockText(iso: string): string {
  const date = new Date(iso);
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

const DEFAULT_CAP = 20;

/** The `done`/`failed` bound (4.12's deferred decision — Design Notes). Newest first
 * (`age_seconds` ascending, the fetch is not itself sorted), capped at `cap`, with the count
 * left out. `queued`/`running`/`needs_you` are never passed through this — they are never
 * capped. */
export function capColumn(
  cards: CardOut[],
  cap: number = DEFAULT_CAP,
): { shown: CardOut[]; more: number } {
  const sorted = [...cards].sort((a, b) => a.age_seconds - b.age_seconds);
  return { shown: sorted.slice(0, cap), more: Math.max(0, sorted.length - cap) };
}

/** The line under a capped column — `''` when nothing was left out, so a caller can render
 * it unconditionally. */
export function moreNotShownText(more: number): string {
  return more > 0 ? `${more} more not shown` : '';
}

/** The request path shown in `FailedFetch`, and the one this island's `api.GET` call always
 * makes — computed rather than read off a `Response.url` so the two can never disagree, and
 * so a network failure (no `Response` at all) still has one to show. */
export function boardRequestPath(projectId: string | null): string {
  const params = new URLSearchParams({ view: 'board' });
  if (projectId) params.set('project_id', projectId);
  return `/api/runs?${params.toString()}`;
}

/** `{method} {path} → {status or "network error"}` (UX-DR4), `FailedFetch`'s command line,
 * verbatim. */
export function fetchFailureMessage(method: string, path: string, status: number | null): string {
  return `${method} ${path} → ${status === null ? 'network error' : status}`;
}

/** Every card across all five columns — the Board's own `{n} runs` and the rail's
 * `Workflows` count both read this. */
export function totalCards(board: BoardOut): number {
  const columns = board.columns;
  return (
    columns.queued.length +
    columns.running.length +
    columns.needs_you.length +
    columns.done.length +
    columns.failed.length
  );
}
