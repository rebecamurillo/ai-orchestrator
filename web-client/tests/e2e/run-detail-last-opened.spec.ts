/**
 * Changed-since-last-opened marks in a real browser (8-3, FR-19, UX-DR9):
 *
 * AC1: First open (`?opened=1`) returns `last_opened_at` and all entries `changed: false`.
 * AC2: Second open with a changed file shows the accent chip on that file's row.
 * AC3: Polling (no `?opened=1`) does not reset the changed marks.
 *
 * `GET /api/runs/{id}/detail` and `GET /api/runs/{id}/files` are mocked with `page.route()`
 * so no real stack is required — the same approach `run-detail-artifacts.spec.ts` already
 * uses for the artifacts column.
 */

import { expect, test, type Page, type Route } from '@playwright/test';

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939ee';
const PAGE_URL = `/workflows/${RUN_ID}`;
const SPEC_FOLDER = 'specs/gates';
const SPEC_FILE = `${SPEC_FOLDER}/SPEC.md`;
const OLD_FILE = `${SPEC_FOLDER}/old.md`;

const LAST_OPENED_AT = '2026-09-11T10:00:00Z';
const MTIME_AFTER = 1_757_592_001; // 1 second after the cutoff (2026-09-11T10:00:00Z)
const MTIME_BEFORE = 1_757_588_399; // before LAST_OPENED_AT

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'needs_you',
    admitted_signals: ['answer', 'cancel'],
    branch: 'epics/gates',
    budget_usd: '40.00',
    compare_urls: [],
    created_at: '2026-09-11T09:00:00Z',
    inputs: { spec_folder: SPEC_FOLDER },
    manual_estimate_h: null,
    plan_ref: 'abc1234',
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '12.30',
    template: 'epic',
    terminal_session: false,
    version: 1,
    worktree_path: '/work/acme/widgets/wt/gates',
    worktrees: [],
    accepted_paths: [],
    last_opened_at: LAST_OPENED_AT,
    ...overrides,
  };
}

function detail(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    header: {
      meta: {
        project: 'Mixed Signals',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: SPEC_FOLDER,
        template: 'epic',
        version: 1,
        harness: 'claude',
        started_at: '2026-09-11T09:00:05Z',
        worktree_path: '/work/acme/widgets/wt/gates',
      },
    },
    alert: {
      token: 'BLK',
      reason: 'Waiting for operator.',
      park_kind: 'blocked',
      attribution: null,
    },
    steps: [],
    stories: [],
    cost: {
      spent_usd: '12.30',
      budget_usd: '40.00',
      tokens_in: 15000,
      tokens_out: 4200,
      wall_clock_seconds: 930,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: ['answer', 'cancel'],
    summary: null,
    ...overrides,
    run: run((overrides.run as Record<string, unknown>) ?? {}),
  };
}

/** Tree where SPEC_FILE was changed after the cutoff, OLD_FILE was not. */
function changedTree(): Record<string, unknown> {
  return {
    root: SPEC_FOLDER,
    entries: [
      { path: SPEC_FILE, kind: 'file', size: 24, mtime: MTIME_AFTER, changed: true },
      { path: OLD_FILE, kind: 'file', size: 8, mtime: MTIME_BEFORE, changed: false },
    ],
  };
}

/** Tree where all files are unchanged (first open). */
function unchangedTree(): Record<string, unknown> {
  return {
    root: SPEC_FOLDER,
    entries: [
      { path: SPEC_FILE, kind: 'file', size: 24, mtime: MTIME_BEFORE, changed: false },
      { path: OLD_FILE, kind: 'file', size: 8, mtime: MTIME_BEFORE, changed: false },
    ],
  };
}

async function mockDetail(page: Page, body: Record<string, unknown>): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

async function mockFiles(page: Page, tree: Record<string, unknown>): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/files**`, (route: Route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.has('path')) {
      // Individual file read — return a minimal file body
      const path = url.searchParams.get('path')!;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ path, content: '# file\n', size: 7, mtime: MTIME_BEFORE }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(tree),
    });
  });
}

async function mockActivity(page: Page): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/activity`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"active_seconds":0}' }),
  );
}

test.describe('changed-since-last-opened marks (8-3)', () => {
  test('AC1: first navigation fetch sends ?opened=true on the detail request', async ({ page }) => {
    const openedRequests: string[] = [];
    await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.get('opened') === 'true') {
        openedRequests.push(route.request().url());
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(detail()),
      });
    });
    await mockFiles(page, unchangedTree());
    await mockActivity(page);

    await page.goto(PAGE_URL);
    await expect(page.getByTestId('wf-header')).toBeVisible();

    expect(openedRequests.length).toBeGreaterThan(0);
  });

  test('AC2: a file with changed=true shows the accent chip', async ({ page }) => {
    await mockDetail(page, detail());
    await mockFiles(page, changedTree());
    await mockActivity(page);

    await page.goto(PAGE_URL);
    await expect(page.getByTestId('artifacts-tree')).toBeVisible();

    // The changed file's button should carry the chip
    const changedButton = page.getByTestId(`artifacts-file-${SPEC_FILE}`);
    await expect(changedButton.locator('.wf-artifacts-chip')).toHaveCount(1);
  });

  test('AC2: a file with changed=false has no chip', async ({ page }) => {
    await mockDetail(page, detail());
    await mockFiles(page, changedTree());
    await mockActivity(page);

    await page.goto(PAGE_URL);
    await expect(page.getByTestId('artifacts-tree')).toBeVisible();

    const unchangedButton = page.getByTestId(`artifacts-file-${OLD_FILE}`);
    await expect(unchangedButton.locator('.wf-artifacts-chip')).toHaveCount(0);
  });

  test('AC3: polling fetch (after first) does not send ?opened=true', async ({ page }) => {
    let requestCount = 0;
    const openedRequests: string[] = [];

    await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) => {
      requestCount++;
      const url = new URL(route.request().url());
      if (url.searchParams.get('opened') === 'true') {
        openedRequests.push(route.request().url());
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(detail({ run: { status: 'running' } })),
      });
    });
    await mockFiles(page, changedTree());
    await mockActivity(page);
    // Must be installed before navigation: `configurePolling`'s `setInterval` is created on
    // the island's first mount effect, and a real interval created before `clock.install()`
    // keeps running on the real clock rather than being virtualised retroactively.
    await page.clock.install();

    await page.goto(PAGE_URL);
    await expect(page.getByTestId('wf-header')).toBeVisible();

    // Advance clock to trigger a poll (RunDetail polls every ~5s while status is `running`)
    await page.clock.fastForward(10_000);
    await expect.poll(() => requestCount).toBeGreaterThan(1);

    // `?opened=true` appeared only once (on the first navigation fetch)
    expect(openedRequests).toHaveLength(1);
  });
});
