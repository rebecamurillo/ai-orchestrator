/**
 * Activity tracking smoke tests (8.2): intercepts `POST /api/runs/{id}/activity` and
 * asserts that loading the Run detail or diagram page causes a POST to fire with
 * `focused_seconds: 60` after advancing the clock 65 s with `page.clock`.
 *
 * `page.clock.install()` / `page.clock.fastForward()` replace the browser's own timers so
 * the test advances 65 s without waiting real seconds — the same mechanism `board.spec.ts`
 * uses for its polling assertions. The backend endpoints are mocked with `page.route()` so
 * no real stack is required.
 */

import { expect, test, type Page, type Route } from '@playwright/test';

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939aa';
const URL = `/workflows/${RUN_ID}`;

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'running',
    admitted_signals: ['cancel'],
    branch: 'epics/8',
    budget_usd: '15.00',
    compare_urls: [],
    created_at: '2026-09-11T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: null,
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '1.00',
    template: 'initiative',
    terminal_session: false,
    version: 1,
    worktree_path: null,
    worktrees: [],
    accepted_paths: [],
    ...overrides,
  };
}

function detail(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    header: {
      meta: {
        project: 'demo',
        repository: 'demo-repo',
        base_branch: 'main',
        folder: 'docs/initiative',
        template: 'initiative',
        version: 1,
        harness: 'claude',
        started_at: '2026-09-11T09:00:05Z',
        worktree_path: null,
      },
    },
    alert: null,
    steps: [],
    stories: [],
    cost: {
      spent_usd: '1.00',
      budget_usd: '15.00',
      tokens_in: 0,
      tokens_out: 0,
      wall_clock_seconds: 0,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: ['cancel'],
    summary: null,
    ...overrides,
    run: run((overrides.run as Record<string, unknown>) ?? {}),
  };
}

async function mockDetail(page: Page, body: Record<string, unknown>): Promise<void> {
  // operator revision 2026-09-18: story 8-3 put `?opened=true` on the first detail fetch; the
  // trailing `**` admits the query string a bare glob never matches. `run-detail-last-opened.
  // spec.ts` AC1/AC3 assert the new behaviour.
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

test.describe('activity tracking (8.2)', () => {
  test('at least one POST /activity fires with a numeric focused_seconds after 65 s', async ({
    page,
  }) => {
    await mockDetail(page, detail());

    // Collect intercepted activity POSTs.
    const activityPosts: { focusedSeconds: number }[] = [];
    await page.route(`**/api/runs/${RUN_ID}/activity`, async (route: Route) => {
      const body = route.request().postDataJSON() as { focused_seconds: number };
      activityPosts.push({ focusedSeconds: body.focused_seconds });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{"active_seconds":60}',
      });
    });

    // Install fake clock before navigation so setInterval is captured by it.
    await page.clock.install();
    await page.goto(URL);

    // Wait for the detail island to hydrate.
    await expect(page.getByTestId('wf-header')).toBeVisible();

    // Ensure the page has focus (document.hasFocus() must be true for ticks to count).
    // Clicking on the header also fires a pointer event that resets the idle timer.
    await page.locator('[data-testid="wf-header"]').click({ force: true });

    // Advance 65 s — enough to trigger the 60 s batch interval.
    await page.clock.runFor(65_000);

    // Give any pending microtasks (the fetch promise) time to settle.
    await page.waitForTimeout(500);

    expect(activityPosts.length).toBeGreaterThanOrEqual(1);
    expect(activityPosts[0].focusedSeconds).toBe(60);
  });

  test('POST /activity fires with focused_seconds: 60 after 65 s on the diagram view', async ({
    page,
  }) => {
    await mockDetail(page, detail());
    // Minimal graph — RunDiagram mounts and startTracking fires regardless of graph content.
    await page.route(`**/api/runs/${RUN_ID}/graph`, (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{"nodes":[],"groups":[],"edges":[],"now_path":null}',
      }),
    );

    const activityPosts: { focusedSeconds: number }[] = [];
    await page.route(`**/api/runs/${RUN_ID}/activity`, async (route: Route) => {
      const body = route.request().postDataJSON() as { focused_seconds: number };
      activityPosts.push({ focusedSeconds: body.focused_seconds });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{"active_seconds":60}',
      });
    });

    // Install fake clock before navigation so setInterval is captured.
    await page.clock.install();
    const graphLoaded = page.waitForResponse(`**/api/runs/${RUN_ID}/graph`);
    await page.goto(`${URL}?view=diagram`);
    await graphLoaded;

    // Give the page focus (document.hasFocus() must be true for ticks to count).
    await page.locator('body').click({ force: true });

    // Advance 65 s — enough to trigger the 60 s batch interval.
    await page.clock.runFor(65_000);
    await page.waitForTimeout(500);

    expect(activityPosts.length).toBeGreaterThanOrEqual(1);
    expect(activityPosts[0].focusedSeconds).toBe(60);
  });
});
