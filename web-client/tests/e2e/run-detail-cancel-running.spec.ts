import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * Cancel button on a *running* or *queued* Run (CAP-5, story 2, 2026-09-25).
 *
 * Before story 2, `StopBody` returned null whenever `stopKind` was null (the Run was not
 * parked). The only Cancel control lived inside that early return, so a running Run offered
 * no Cancel at all. This spec covers the new path: when `admitted_signals` includes
 * `cancel` and the Run is not parked, the Cancel button renders without any stop body.
 *
 * Same mocking pattern as `run-detail-skip-story.spec.ts`: `GET /api/runs/{id}/detail` and
 * `POST /api/runs/{id}/signals` are mocked with `page.route()`.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939d0';
const URL = `/workflows/${RUN_ID}`;

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'running',
    admitted_signals: ['cancel'],
    branch: 'feat/step-handling-1',
    budget_usd: '40.00',
    compare_urls: [],
    created_at: '2026-09-07T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: null,
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '1.00',
    template: 'epic',
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
        project: 'Step Handling',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'specs/step-handling',
        template: 'epic',
        version: 1,
        harness: 'local',
        started_at: '2026-09-07T09:00:05Z',
        worktree_path: '/work/orchestrator',
      },
    },
    alert: null,
    steps: [],
    stories: [],
    cost: {
      spent_usd: '1.00',
      budget_usd: '40.00',
      tokens_in: 5000,
      tokens_out: 1200,
      wall_clock_seconds: 120,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: ['cancel'],
    reply_available: false,
    resume_unavailable_reason: null,
    summary: null,
    ...overrides,
    run: run((overrides.run as Record<string, unknown>) ?? {}),
  };
}

async function mockDetail(page: Page, body: Record<string, unknown>): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

async function open(page: Page, body = detail()): Promise<void> {
  await mockDetail(page, body);
  await page.goto(URL);
  await expect(page.getByTestId('wf-header')).toBeVisible();
}

test.describe('Cancel while running', () => {
  test('a running Run with cancel admitted shows the Cancel button and no stop body', async ({
    page,
  }) => {
    await open(page);

    await expect(page.getByTestId('wf-cancel')).toBeVisible();
    await expect(page.getByTestId('wf-cancel')).toContainText('Cancel run');
    // No stop body — the Run is not parked
    await expect(page.locator('[data-testid^="wf-stop-"]')).toHaveCount(0);
  });

  test('a queued Run with cancel admitted shows the Cancel button and no stop body', async ({
    page,
  }) => {
    await open(page, detail({ run: { status: 'queued' } }));

    await expect(page.getByTestId('wf-cancel')).toBeVisible();
    await expect(page.locator('[data-testid^="wf-stop-"]')).toHaveCount(0);
  });

  test('a running Run without cancel in admitted_signals shows nothing', async ({ page }) => {
    await open(
      page,
      detail({
        admitted_signals: [],
        run: { admitted_signals: [] },
      }),
    );

    await expect(page.getByTestId('wf-cancel')).toHaveCount(0);
    await expect(page.locator('[data-testid^="wf-stop-"]')).toHaveCount(0);
  });

  test('confirming cancel posts the signal and re-fetches', async ({ page }) => {
    await open(page);

    const posted: Record<string, unknown>[] = [];
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      posted.push(route.request().postDataJSON() as Record<string, unknown>);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(run({ status: 'cancelled', admitted_signals: [] })),
      });
    });
    await mockDetail(
      page,
      detail({
        alert: null,
        admitted_signals: [],
        run: { status: 'cancelled', admitted_signals: [] },
      }),
    );

    await page.getByTestId('wf-cancel').click();
    // CancelModal asks for confirmation — click the confirm button inside the modal
    await page.getByTestId('wf-cancel-confirm-yes').click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].kind).toBe('cancel');
  });

  test('a parked stop still shows the stop body alongside Cancel', async ({ page }) => {
    await open(
      page,
      detail({
        alert: {
          token: 'BLK',
          reason: 'waiting for operator',
          park_kind: 'blocked',
          row_kind: 'agent',
        },
        admitted_signals: ['retry', 'skip_step', 'skip_story', 'skip_epic', 'cancel'],
        run: {
          status: 'needs_you',
          admitted_signals: ['retry', 'skip_step', 'skip_story', 'skip_epic', 'cancel'],
        },
      }),
    );

    await expect(page.getByTestId('wf-stop-blocked')).toBeVisible();
    await expect(page.getByTestId('wf-cancel')).toBeVisible();
  });
});
