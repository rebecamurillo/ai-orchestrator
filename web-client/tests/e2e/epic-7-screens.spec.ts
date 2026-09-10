import { fileURLToPath, URL as NodeUrl } from 'node:url';

import { expect, test, type Page, type Route } from '@playwright/test';

import { EXPORT_ID } from './projects-fixtures.mjs';

/**
 * Epic 7's own screenshot deliverable: one PNG per new screen the epic added (7.5's HISTORY
 * table, twice — bare and filtered — and 7.6's *Export trajectories*), captured while this
 * spec runs under `make e2e-ui` — the same mechanism `run-detail-epic-6-screens.spec.ts`'s own
 * module doc describes for Epic 6, and `run-detail-story-additions.spec.ts`'s for Epic 5.
 * There is no engine here — every state below is about rendering a given response, not
 * producing one — so each fixture is lifted from the specs Epic 7 already added rather than
 * invented here: `runs-history.spec.ts`'s own `historyRow`/`mockHistory`/`mockQueueEmpty` shape
 * for the HISTORY screens, and `trajectory-export.spec.ts` (with `projects-fixtures.mjs`'s
 * `EXPORT_ID` project) for the Project export screen.
 *
 * New file, for the reason every one of those gives: `runs-history.spec.ts` and
 * `trajectory-export.spec.ts` are frozen and exist to prove behaviour, not to produce PNGs.
 *
 * **A fourth state is not captured here.** 7-3's own AC — the New workflow MODEL field
 * becoming a `<select>` over the `LOCAL_MODELS` aliases once harness `local` is chosen — needs
 * `GET /api/v1/harnesses` to answer an *enabled* `local` carrying a `models` list
 * (`newwf-model-select.test.ts`'s own `HARNESSES` fixture). `new.astro` reads that route from
 * its own frontmatter with `backend()` (`src/api/server.ts`) — a server-side fetch straight to
 * `BACKEND_API_URL`, issued before the browser is ever given a response — so `page.route()`,
 * which only intercepts requests the page itself makes, cannot reshape it. The only place that
 * fetch resolves against is `tests/e2e/stub-backend.mjs`'s static `HARNESSES` array, seeded
 * `local: { enabled: false }` with no `models` key and read by every spec in this suite; giving
 * it one here would be editing an existing stub, which hard rule 1 forbids and this file does
 * not do. This matches `_bmad-output/implementation-artifacts/epic-7-handoff.md`'s own
 * accounting (§6): the select-over-`LOCAL_MODELS` behaviour is listed as proved "on the
 * compose stack, against real Postgres and the real walker" — a real `backend-api` with
 * `LOCAL_MODELS` configured and a `local` harness enabled, not the stub this gate runs
 * against. Producing this PNG for real needs that stack, not `make e2e-ui`.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939cc';
const SCREENS = fileURLToPath(
  new NodeUrl('../../../_bmad-output/implementation-artifacts/epic-7-screens', import.meta.url),
);

// A real desktop layout, not a collapsed mobile column.
test.use({ viewport: { width: 1440, height: 900 } });

/** The exact shape `runs-history.spec.ts`'s own `historyRow()` fixture uses. */
function historyRow(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    attempt_id: '00000000-0000-0000-0000-000000000001',
    run_id: RUN_ID,
    seq: 7,
    started_at: '2026-09-09T08:04:05Z',
    ended_at: '2026-09-09T08:06:35Z',
    seconds: 150,
    project_name: 'Mixed Signals',
    run_label: 'epic v2 · epics/gates',
    path: 'epics[0].stories[3].build',
    kind: 'agent',
    harness: 'claude',
    model: 'claude-opus-4',
    session_id: 'sess-1',
    status: 'done',
    token: 'DON',
    tokens_in: 100,
    tokens_out: 20,
    cost_usd: '0.250000',
    cost_provisional: false,
    trace_url: 'https://langfuse.test/traces/1',
    log_tail_url: `/api/v1/runs/${RUN_ID}/detail`,
    ...overrides,
  };
}

/** The harness-comparison table Epic 7 exists for: claude, codex and local side by side,
 * agent rows beside non-agent ones, and every status colour the history can show. */
const CLAUDE_DONE = historyRow({
  attempt_id: '00000000-0000-0000-0000-0000000000a1',
  seq: 12,
  started_at: '2026-09-09T08:04:05Z',
  ended_at: '2026-09-09T08:06:35Z',
  seconds: 150,
  path: 'epics[0].stories[3].build',
  harness: 'claude',
  model: 'claude-opus-4',
  session_id: 'sess-claude-1',
  status: 'done',
  token: 'DON',
  tokens_in: 15000,
  tokens_out: 4200,
  cost_usd: '3.200000',
  trace_url: 'https://langfuse.test/traces/11',
});
const CODEX_RUNNING = historyRow({
  attempt_id: '00000000-0000-0000-0000-0000000000a2',
  seq: 13,
  started_at: '2026-09-09T08:10:00Z',
  ended_at: null,
  seconds: null,
  path: 'epics[0].stories[4].build',
  harness: 'codex',
  model: 'gpt-5-codex',
  session_id: 'sess-codex-1',
  status: 'running',
  token: 'RUN',
  tokens_in: 8000,
  tokens_out: 1200,
  cost_usd: '1.100000',
  cost_provisional: true,
  trace_url: 'https://langfuse.test/traces/12',
});
// A local model's own cost fact (PRD §11, `history.ts::costText`'s own note): `0.000000` with
// real tokens beside it is a cost of zero, not an absent one.
const LOCAL_DONE = historyRow({
  attempt_id: '00000000-0000-0000-0000-0000000000a3',
  seq: 11,
  started_at: '2026-09-09T07:50:00Z',
  ended_at: '2026-09-09T07:54:10Z',
  seconds: 250,
  path: 'epics[0].stories[2].build',
  harness: 'local',
  model: 'local-coder',
  session_id: 'sess-local-1',
  status: 'done',
  token: 'DON',
  tokens_in: 22000,
  tokens_out: 5000,
  cost_usd: '0.000000',
  trace_url: null,
});
const CLAUDE_BLOCKED = historyRow({
  attempt_id: '00000000-0000-0000-0000-0000000000a4',
  seq: 14,
  started_at: '2026-09-09T08:20:00Z',
  ended_at: '2026-09-09T08:21:00Z',
  seconds: 60,
  path: 'epics[0].stories[5].build',
  harness: 'claude',
  model: 'claude-opus-4',
  session_id: 'sess-claude-2',
  status: 'blocked',
  token: 'BLK',
  tokens_in: 3000,
  tokens_out: 900,
  cost_usd: '0.800000',
  trace_url: 'https://langfuse.test/traces/14',
});
const GIT_COMMIT = historyRow({
  attempt_id: '00000000-0000-0000-0000-0000000000a5',
  seq: 10,
  started_at: '2026-09-09T07:45:00Z',
  ended_at: '2026-09-09T07:45:02Z',
  seconds: 2,
  path: 'epics[0].stories[2].commit',
  kind: 'git.commit',
  harness: null,
  model: null,
  session_id: null,
  status: 'done',
  token: 'DON',
  tokens_in: null,
  tokens_out: null,
  cost_usd: null,
  trace_url: null,
});
const GIT_PUSH_FAILED = historyRow({
  attempt_id: '00000000-0000-0000-0000-0000000000a6',
  seq: 15,
  started_at: '2026-09-09T08:22:00Z',
  ended_at: '2026-09-09T08:22:05Z',
  seconds: 5,
  path: 'epics[0].push',
  kind: 'git.push',
  harness: null,
  model: null,
  session_id: null,
  status: 'error',
  token: 'ERR',
  tokens_in: null,
  tokens_out: null,
  cost_usd: null,
  trace_url: null,
});

/** The exact shape `runs-history.spec.ts`'s own `mockHistory()` uses. */
async function mockHistory(page: Page, body: Record<string, unknown>): Promise<void> {
  await page.route('**/api/steps*', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

/** The exact shape `runs-history.spec.ts`'s own `mockQueueEmpty()` uses — the QUEUE section is
 * not this deliverable's subject, so it is left forced empty. */
async function mockQueueEmpty(page: Page): Promise<void> {
  await page.route('**/api/queue*', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], next_cursor: null, max_active_runs: 2 }),
    }),
  );
}

test.describe('Epic 7 screens', () => {
  test('01 — the HISTORY table, three harnesses and the more control', async ({ page }) => {
    await mockQueueEmpty(page);
    await mockHistory(page, {
      items: [CLAUDE_DONE, CODEX_RUNNING, LOCAL_DONE, CLAUDE_BLOCKED, GIT_COMMIT, GIT_PUSH_FAILED],
      next_cursor: 'CURSOR-1',
    });

    await page.goto('/runs');
    await expect(page.getByTestId('runs-history')).toBeVisible();
    await expect(page.getByTestId('runs-history')).toContainText('HISTORY');
    await expect(page.getByTestId('runs-history').locator('tbody tr')).toHaveCount(6);
    await expect(page.getByTestId('runs-history-more')).toBeVisible();

    await page.screenshot({ path: `${SCREENS}/01-runs-history.png`, fullPage: true });
  });

  test('02 — the same table with a status filter applied', async ({ page }) => {
    await mockQueueEmpty(page);
    await mockHistory(page, { items: [CLAUDE_BLOCKED], next_cursor: null });

    await page.goto('/runs?status=BLK');
    await expect(page.getByTestId('runs-history')).toBeVisible();
    await expect(
      page.getByTestId('runs-filter-status').locator('a[aria-current="true"]'),
    ).toHaveText('BLK');
    await expect(page.getByTestId('runs-history').locator('tbody tr')).toHaveCount(1);

    await page.screenshot({ path: `${SCREENS}/02-runs-history-filtered.png`, fullPage: true });
  });

  test('03 — the Project screen, Export trajectories with its hint and count', async ({ page }) => {
    // The exact shape `trajectory-export.spec.ts` uses — real stub data, not a `page.route()`
    // mock (that spec's own module doc says why): `EXPORT_ID` names `EXPORT`, the Project
    // `projects-fixtures.mjs` seeds with `trajectory_count: EXPORT_TRAJECTORY_COUNT`.
    await page.goto(`/projects?id=${EXPORT_ID}`);

    const exportButton = page.getByTestId('projects-export');
    await expect(exportButton).toBeVisible();
    await expect(exportButton).toHaveAttribute(
      'href',
      `/api/projects/${EXPORT_ID}/trajectories.jsonl`,
    );
    await expect(page.getByTestId('projects-export-hint')).toContainText('trajectories');

    await page.screenshot({
      path: `${SCREENS}/03-project-export-trajectories.png`,
      fullPage: true,
    });
  });
});
