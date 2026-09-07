import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * The Runs screen's QUEUE section (4.16, SPEC CAP-16, FR-25, UX-DR14).
 *
 * `GET /api/v1/queue` answers unconditionally empty in the shared stub (this story's own
 * addition to `stub-backend.mjs`, `board.spec.ts`'s own "`GET /api/v1/projects` answers an
 * empty list unconditionally" precedent — needed for the frozen `shell.spec.ts`'s own
 * "`NO RUNS` at bare `/runs`" reading), so every real-content scenario here mocks
 * `GET /api/queue` with `page.route()` instead — there is no engine here to hold a real
 * queue, and the ACs are about rendering a given response, `board.spec.ts`'s own precedent
 * for `GET /runs?view=board`.
 *
 * `openQueue` waits on `runs-queue` as its hydration gate: the island renders nothing at all
 * until its first fetch resolves (`RunDetail.tsx`'s own pattern, `new-workflow.spec.ts`'s
 * `openForm` precedent for why an explicit gate matters), and `runs-queue` wraps both the
 * populated table and the empty reading, so it is the one element every ready state shares.
 */

const RUN_1 = '11111111-1111-1111-1111-111111111111';
const RUN_2 = '22222222-2222-2222-2222-222222222222';
const RUN_3 = '33333333-3333-3333-3333-333333333333';
const RUN_4 = '44444444-4444-4444-4444-444444444444';

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_1,
    status: 'running',
    template: 'initiative',
    version: 1,
    project: '55555555-5555-5555-5555-555555555555',
    repository: '66666666-6666-6666-6666-666666666666',
    branch: 'epics/1',
    budget_usd: '15.00',
    spend_usd: '2.50',
    plan_ref: 'abc123',
    created_at: '2026-09-07T09:00:00Z',
    admitted_signals: [],
    ...overrides,
  };
}

function row(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    position: null,
    run: run(),
    next_step_label: 'plan',
    reason: 'running',
    waiting_since: '2026-09-07T09:00:00Z',
    waiting_seconds: 90,
    ...overrides,
  };
}

function queueResponse(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    items: [],
    next_cursor: null,
    max_active_runs: 2,
    ...overrides,
  };
}

async function mockQueue(page: Page, body: unknown): Promise<void> {
  await page.route('**/api/queue*', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

async function openQueue(page: Page, url: string = '/runs'): Promise<void> {
  await page.goto(url);
  await expect(page.getByTestId('runs-queue')).toBeVisible();
}

test.describe('/runs (QUEUE section)', () => {
  test('an active Run, one on the lock, one on global concurrency, and one parked: four rows, the fixed positions and reasons, the hint, and the concurrency figure in the head', async ({
    page,
  }) => {
    await mockQueue(
      page,
      queueResponse({
        items: [
          row({ position: null, reason: 'running', run: run({ id: RUN_1 }) }),
          row({
            position: 1,
            reason: 'repository lock held by initiative v1 · epics/1',
            run: run({ id: RUN_2, template: 'epic', version: 2, branch: 'epics/2' }),
          }),
          row({
            position: 2,
            reason: 'global concurrency, held by initiative v1 · epics/1, epic v2 · epics/2',
            run: run({ id: RUN_3, template: 'initiative', version: 1, branch: 'epics/3' }),
          }),
          row({
            position: null,
            reason: 'waiting for your answer',
            next_step_label: 'checkpoint',
            run: run({ id: RUN_4, template: 'epic', version: 1, branch: 'epics/4' }),
          }),
        ],
        max_active_runs: 2,
      }),
    );
    await openQueue(page);

    await expect(page.getByTestId('runs-queue')).toContainText('concurrency 2');

    const running = page.getByTestId(`runs-queue-row-${RUN_1}`);
    await expect(running).toContainText('running');
    await expect(running.locator('td').first()).toHaveText('—');

    const lockHeld = page.getByTestId(`runs-queue-row-${RUN_2}`);
    await expect(lockHeld).toContainText('repository lock held by initiative v1 · epics/1');
    await expect(lockHeld.locator('td').first()).toHaveText('1');

    const globalConcurrency = page.getByTestId(`runs-queue-row-${RUN_3}`);
    await expect(globalConcurrency).toContainText(
      'global concurrency, held by initiative v1 · epics/1, epic v2 · epics/2',
    );
    await expect(globalConcurrency.locator('td').first()).toHaveText('2');

    const parked = page.getByTestId(`runs-queue-row-${RUN_4}`);
    await expect(parked).toContainText('waiting for your answer');
    await expect(parked).toContainText('not queued until then');
    await expect(parked.locator('td').first()).toHaveText('—');
  });

  test('the workflow cell reads `{template} v{n} · {branch}` and links to the run detail', async ({
    page,
  }) => {
    await mockQueue(
      page,
      queueResponse({
        items: [
          row({
            position: 1,
            reason: 'repository lock held by initiative v1 · epics/1',
            run: run({ id: RUN_2, template: 'epic', version: 3, branch: 'epics/9' }),
          }),
        ],
      }),
    );
    await openQueue(page);

    const cell = page.getByTestId(`runs-queue-row-${RUN_2}`).getByRole('link');
    await expect(cell).toHaveText('epic v3 · epics/9');
    await expect(cell).toHaveAttribute('href', `/workflows/${RUN_2}`);

    await cell.click();
    await expect(page).toHaveURL(new RegExp(`/workflows/${RUN_2}$`));
  });

  test('an empty queue reads nothing queued', async ({ page }) => {
    await mockQueue(page, queueResponse());
    await openQueue(page);

    await expect(page.getByTestId('runs-queue')).toContainText('nothing queued');
    await expect(page.locator('table.runs-queue-table')).toHaveCount(0);
  });

  test('the table updates on the next poll tick with no reload', async ({ page }) => {
    let parked = false;
    await page.route('**/api/queue*', (route: Route) => {
      if (!parked) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(
            queueResponse({
              items: [row({ position: null, reason: 'running', run: run({ id: RUN_1 }) })],
            }),
          ),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          queueResponse({
            items: [
              row({ position: null, reason: 'waiting for your answer', run: run({ id: RUN_4 }) }),
            ],
          }),
        ),
      });
    });

    // installed before navigation: `configurePolling`'s `setInterval` is created on the
    // island's first mount effect, and a real interval created before `clock.install()`
    // keeps running on the real clock rather than being virtualised retroactively
    // (`board.spec.ts`'s own precedent)
    await page.clock.install();
    await openQueue(page);
    await expect(page.getByTestId(`runs-queue-row-${RUN_1}`)).toBeVisible();

    // the first response's own reason is `running`, so `$poll` ticks at 5s
    parked = true;
    await page.clock.fastForward(5_500);

    await expect(page.getByTestId(`runs-queue-row-${RUN_4}`)).toBeVisible();
    await expect(page.getByTestId(`runs-queue-row-${RUN_1}`)).toHaveCount(0);
  });

  test('a failed poll shows the full-surface readout; Retry restores it', async ({ page }) => {
    let fail = true;
    await page.route('**/api/queue*', (route: Route) => {
      if (fail) {
        return route.fulfill({
          status: 500,
          contentType: 'application/problem+json',
          body: JSON.stringify({ type: 'about:blank', title: 'error', status: 500 }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(queueResponse()),
      });
    });

    await page.goto('/runs');

    await expect(page.getByTestId('fetch-failed')).toBeVisible();
    await expect(page.getByTestId('fetch-failed')).toContainText('GET /api/queue');
    await expect(page.getByTestId('fetch-failed')).toContainText('500');

    fail = false;
    await page.getByTestId('fetch-retry').click();

    await expect(page.getByTestId('runs-queue')).toBeVisible();
    await expect(page.getByTestId('fetch-failed')).toHaveCount(0);
  });

  test('the bar carries the project and status filters, and the History section head', async ({
    page,
  }) => {
    await mockQueue(page, queueResponse());
    await openQueue(page);

    const statusFilter = page.getByTestId('runs-filter-status');
    for (const token of ['ALL', 'QUE', 'RUN', 'BLK', 'ERR', 'DON']) {
      await expect(statusFilter.getByRole('link', { name: token, exact: true })).toBeVisible();
    }
    await expect(
      page.getByTestId('runs-filter-project').getByRole('link', { name: 'all' }),
    ).toHaveAttribute('aria-current', 'true');

    await expect(page.getByTestId('runs-history')).toContainText(
      'history arrives with the harness comparison epic',
    );
  });

  test('a status filter link carries the right href and flips aria-current; a project param already in the URL survives on every status link', async ({
    page,
  }) => {
    await mockQueue(page, queueResponse());
    const projectId = '77777777-7777-7777-7777-777777777777';

    await openQueue(page, `/runs?project=${projectId}&status=RUN`);

    const statusFilter = page.getByTestId('runs-filter-status');
    await expect(statusFilter.getByRole('link', { name: 'RUN', exact: true })).toHaveAttribute(
      'aria-current',
      'true',
    );
    await expect(statusFilter.getByRole('link', { name: 'ALL', exact: true })).not.toHaveAttribute(
      'aria-current',
      'true',
    );
    // every status link keeps the project param already in the URL, `ALL` drops its own
    // (the default carries no `status=` at all — `filterHref`'s own early-return branch)
    await expect(statusFilter.getByRole('link', { name: 'ALL', exact: true })).toHaveAttribute(
      'href',
      `/runs?project=${projectId}`,
    );
    await expect(statusFilter.getByRole('link', { name: 'BLK', exact: true })).toHaveAttribute(
      'href',
      `/runs?project=${projectId}&status=BLK`,
    );

    // the project filter's own "all" link keeps the status param, and drops only `project=`
    await expect(
      page.getByTestId('runs-filter-project').getByRole('link', { name: 'all' }),
    ).toHaveAttribute('href', '/runs?status=RUN');
  });

  test('an unrecognized ?status= falls back to ALL rather than leaving every link unmarked', async ({
    page,
  }) => {
    await mockQueue(page, queueResponse());
    await openQueue(page, '/runs?status=NOT_A_TOKEN');

    await expect(
      page.getByTestId('runs-filter-status').getByRole('link', { name: 'ALL', exact: true }),
    ).toHaveAttribute('aria-current', 'true');
  });

  test('bare /runs (no run has ever started) reads NO RUNS, inside the shell', async ({ page }) => {
    await page.goto('/runs');

    await expect(page.getByTestId('runs-empty')).toContainText('NO RUNS');
    await expect(page.getByTestId('runs-empty')).toContainText('nothing queued');
  });
});
