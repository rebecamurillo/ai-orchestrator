/**
 * Pure reads over a Project's `runs[]` (4.10, UX-DR12, SPEC CAP-10): the Repository row's
 * `Initialise repository` control state, and the age text the **RUNS ON THIS PROJECT** list
 * shows. Kept out of `index.astro`'s frontmatter so it unit-tests without rendering, the way
 * `ProjectForm.tsx`'s own logic lives in `project-form-logic.ts`.
 */
import type { components } from '../../api/schema';

export type ProjectRunOut = components['schemas']['ProjectRunOut'];

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

/**
 * `"2d 04h"`, `"3h 07m"`, `"12m"` — never more than two units, and never negative: a clock
 * skew that puts `createdAt` a moment after `now` reads `"0m"` rather than a negative age.
 */
export function ageText(createdAt: string, now: Date): string {
  const elapsed = Math.max(0, now.getTime() - new Date(createdAt).getTime());
  if (elapsed >= DAY_MS) {
    const days = Math.floor(elapsed / DAY_MS);
    const hours = Math.floor((elapsed % DAY_MS) / HOUR_MS);
    return `${days}d ${String(hours).padStart(2, '0')}h`;
  }
  if (elapsed >= HOUR_MS) {
    const hours = Math.floor(elapsed / HOUR_MS);
    const minutes = Math.floor((elapsed % HOUR_MS) / MINUTE_MS);
    return `${hours}h ${String(minutes).padStart(2, '0')}m`;
  }
  return `${Math.floor(elapsed / MINUTE_MS)}m`;
}

/**
 * The Repository's own most recent initialisation Run, or `null` when it has never had one —
 * what a row's own `Initialise repository` control reads. Which Run that is comes from the
 * server (`ProjectRunOut.is_init`, resolved against `INIT_TEMPLATE`), never from a Template
 * name tested here: the shipped one is an exemplar and an instance may configure its own
 * (Operator decision 2026-09-30: no template name hardcoded in product code). `runs` arrives
 * newest-first already (`GET /projects/{id}`'s own contract, `RunRepository.list`, 4.1), so
 * the first match is the most recent one.
 */
export function latestInitRun(runs: ProjectRunOut[], repositoryId: string): ProjectRunOut | null {
  return runs.find((run) => run.repository_id === repositoryId && run.is_init) ?? null;
}
