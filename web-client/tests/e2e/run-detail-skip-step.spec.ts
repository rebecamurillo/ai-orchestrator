import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * *Skip step* and its inline confirm in a real browser (CAP-1, story 1, 2026-09-25).
 *
 * The confirm is the half the unit test cannot reach: `run-stop-body-skip-step.test.ts` uses
 * `renderToStaticMarkup` which cannot assert callbacks, so `onConfirm` wiring would be
 * undetected there. This spec drives a real browser, which means clicking the confirm
 * button and verifying the signal posts.
 *
 * Same mocking pattern as `run-detail-skip-story.spec.ts`: `GET /api/runs/{id}/detail` and
 * `POST /api/runs/{id}/signals` are mocked with `page.route()` — there is no engine here
 * to park a real step, and every assertion is about what the screen does with a given response.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939cf';
const URL = `/workflows/${RUN_ID}`;

const BUILD = 'epics[0].stories[0].build';

const CONFIRM_LINE = `skip ${BUILD}: marks it skipped and continues at the next row`;

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'needs_you',
    admitted_signals: ['retry', 'skip_step', 'skip_story', 'skip_epic', 'cancel'],
    branch: 'epics/1',
    budget_usd: '40.00',
    compare_urls: [],
    created_at: '2026-09-07T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: null,
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '12.30',
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
        project: 'Mixed Signals',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'specs/gates',
        template: 'epic',
        version: 1,
        harness: 'fake',
        started_at: '2026-09-07T09:00:05Z',
        worktree_path: '/work/orchestrator',
      },
    },
    alert: {
      token: 'ERR',
      reason: 'exit 1',
      park_kind: 'verify_failed',
      row_kind: 'shell',
    },
    steps: [
      {
        seq: 1,
        path: BUILD,
        label: 'build',
        kind: 'agent',
        gate: 'liveness',
        status: 'error',
        token: 'ERR',
        reason: 'exit 1',
        attempts: 1,
        latest: null,
      },
    ],
    stories: [{ epic_index: 1, story_id: '4-1', state: 'current', cost_usd: '3.20' }],
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
    // The park's own gate record, as `_alert` publishes it for every stop: `currentStepPath`
    // (`src/lib/run/detail.ts`) reads the parked row's path off the last record matching the
    // alert's `park_kind`, and the confirm line names that path. A stop with an empty
    // `gate_record` is a state no parked Run can be in — `record()` writes the entry in the
    // same transaction as the park (AD-8) — so the fixture carries it (fixture defect fixed
    // 2026-09-26; the assertion it made possible is unchanged and now reachable).
    gate_record: [
      {
        id: 'g1',
        at: '2026-09-07T09:11:00Z',
        path: BUILD,
        event: 'verify_failed',
        actor: 'machine',
        text: 'exit 1',
        attempt_n: 1,
      },
    ],
    admitted_signals: ['retry', 'skip_step', 'skip_story', 'skip_epic', 'cancel'],
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

test.describe('Skip step', () => {
  test('a stop with skip_step admitted offers it, and clicking states what it will do', async ({
    page,
  }) => {
    await open(page);

    await expect(page.getByTestId('wf-confirm-skip_step')).toHaveCount(0);
    await page.getByTestId('wf-signal-skip_step').click();

    await expect(page.getByTestId('wf-confirm-skip_step-line')).toHaveText(CONFIRM_LINE);
    await expect(page.getByTestId('wf-confirm-skip_step-yes')).toBeVisible();
    await expect(page.getByTestId('wf-confirm-skip_step-keep')).toBeVisible();
  });

  test('confirming posts skip_step once and re-fetches', async ({ page }) => {
    await open(page);

    const posted: Record<string, unknown>[] = [];
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      posted.push(route.request().postDataJSON() as Record<string, unknown>);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(run({ status: 'running' })),
      });
    });
    await mockDetail(page, detail({ run: { status: 'running' }, alert: null }));

    await page.getByTestId('wf-signal-skip_step').click();
    await page.getByTestId('wf-confirm-skip_step-yes').click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].kind).toBe('skip_step');
    await expect(page.getByTestId('wf-stop-verify_failed')).toHaveCount(0);
  });

  test('Keep posts nothing and puts the button back', async ({ page }) => {
    await open(page);

    let calls = 0;
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      calls += 1;
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.getByTestId('wf-signal-skip_step').click();
    await page.getByTestId('wf-confirm-skip_step-keep').click();

    await expect(page.getByTestId('wf-signal-skip_step')).toBeVisible();
    await expect(page.getByTestId('wf-confirm-skip_step')).toHaveCount(0);
    expect(calls).toBe(0);
  });

  test('skip_step is absent when not in admitted_signals', async ({ page }) => {
    await open(
      page,
      detail({
        admitted_signals: ['retry', 'skip_story', 'skip_epic', 'cancel'],
        run: { admitted_signals: ['retry', 'skip_story', 'skip_epic', 'cancel'] },
      }),
    );

    await expect(page.getByTestId('wf-signal-skip_step')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-skip_story')).toBeVisible();
  });
});
