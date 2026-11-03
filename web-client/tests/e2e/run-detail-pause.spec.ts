import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * *Pause* beside *Cancel run* on a running Run, and the `paused` stop it lands as (CAP-8,
 * story 2-1). `GET /api/runs/{id}/detail` and `POST /api/runs/{id}/signals` are mocked with
 * `page.route()`: there is no engine here to park a real step, and every assertion is about
 * what the screen does with a given response.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939cf';
const URL = `/workflows/${RUN_ID}`;
const VERIFY = 'stories[0].verify';
const PARK_SEQ = 3;

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'running',
    admitted_signals: ['pause', 'cancel'],
    branch: 'epics/1',
    budget_usd: '40.00',
    compare_urls: [],
    created_at: '2026-11-02T09:00:00Z',
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
        project: 'Mixed Signals',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'specs/gates',
        template: 'epic',
        version: 1,
        harness: 'fake',
        started_at: '2026-11-02T09:00:05Z',
        worktree_path: '/work/orchestrator',
      },
    },
    alert: null,
    steps: [
      {
        seq: 1,
        path: VERIFY,
        label: 'verify',
        kind: 'shell',
        gate: 'deterministic',
        status: 'running',
        token: 'RUN',
        reason: null,
        attempts: 1,
        latest: null,
      },
    ],
    stories: [{ epic_index: 1, story_id: '2-1', state: 'current', cost_usd: '1.00' }],
    cost: {
      spent_usd: '1.00',
      budget_usd: '40.00',
      tokens_in: 1000,
      tokens_out: 200,
      wall_clock_seconds: 60,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: ['pause', 'cancel'],
    reply_available: false,
    resume_unavailable_reason: null,
    summary: null,
    ...overrides,
    run: run((overrides.run as Record<string, unknown>) ?? {}),
  };
}

function paused(): Record<string, unknown> {
  const admitted = ['continue', 'cancel'];
  return detail({
    alert: {
      token: 'CHK',
      reason: `paused at the Operator's request; next: ${VERIFY}`,
      park_kind: 'paused',
      row_kind: 'shell',
    },
    gate_record: [
      {
        id: 'g1',
        at: '2026-11-02T09:11:00Z',
        path: VERIFY,
        event: 'paused',
        actor: 'machine',
        text: `paused at the Operator's request; next: ${VERIFY}`,
        attempt_n: null,
      },
    ],
    admitted_signals: admitted,
    run: { status: 'needs_you', admitted_signals: admitted, park_seq: PARK_SEQ },
  });
}

async function open(page: Page, body: Record<string, unknown>): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
  await page.goto(URL);
  await expect(page.getByTestId('wf-header')).toBeVisible();
}

test.describe('Pause', () => {
  test('a running Run offers Pause beside Cancel run, and clicking states what it will do', async ({
    page,
  }) => {
    await open(page, detail());

    await expect(page.getByTestId('wf-cancel')).toBeVisible();
    await expect(page.getByTestId('wf-confirm-pause')).toHaveCount(0);
    await page.getByTestId('wf-signal-pause').click();

    await expect(page.getByTestId('wf-confirm-pause-line')).toContainText('nothing is killed');
    await expect(page.getByTestId('wf-confirm-pause-yes')).toBeVisible();
    await expect(page.getByTestId('wf-confirm-pause-keep')).toBeVisible();
  });

  test('confirming posts pause once, with no stop, and the request line replaces the button', async ({
    page,
  }) => {
    await open(page, detail());

    const posted: Record<string, unknown>[] = [];
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      posted.push(route.request().postDataJSON() as Record<string, unknown>);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(run({ pause_requested: true, admitted_signals: ['cancel'] })),
      });
    });
    await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          detail({ admitted_signals: ['cancel'], run: { pause_requested: true } }),
        ),
      }),
    );

    await page.getByTestId('wf-signal-pause').click();
    await page.getByTestId('wf-confirm-pause-yes').click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({ kind: 'pause' });
    await expect(page.getByTestId('wf-pause-requested')).toBeVisible();
    await expect(page.getByTestId('wf-signal-pause')).toHaveCount(0);
  });

  test('Keep posts nothing and puts the button back', async ({ page }) => {
    await open(page, detail());

    let calls = 0;
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      calls += 1;
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.getByTestId('wf-signal-pause').click();
    await page.getByTestId('wf-confirm-pause-keep').click();

    await expect(page.getByTestId('wf-signal-pause')).toBeVisible();
    expect(calls).toBe(0);
  });

  test('a paused stop offers Continue and Cancel run, and Continue names the stop', async ({
    page,
  }) => {
    await open(page, paused());

    await expect(page.getByTestId('wf-stop-paused')).toContainText(VERIFY);
    await expect(page.getByTestId('wf-signal-pause')).toHaveCount(0);
    await expect(page.getByTestId('wf-cancel')).toBeVisible();

    const posted: Record<string, unknown>[] = [];
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      posted.push(route.request().postDataJSON() as Record<string, unknown>);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(run()),
      });
    });
    await page.getByTestId('wf-signal-continue').click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({ kind: 'continue', stop: PARK_SEQ });
  });
});
