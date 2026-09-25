import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * `RetryBox` — mode selector, text field, and resume-unavailable reasons in a real
 * browser (CAP-2, CAP-3, story 4, 2026-09-25).
 *
 * The unit tests cover static markup; this spec covers what a browser sees: the session
 * radio defaulting, the unavailability messages rendering, the text field accepting input,
 * and the Retry button posting `{mode, text}` through `RetryBox.onRetry` →
 * `RunDetail.sendSignal('retry', retryBody(mode, text))`.
 *
 * Same mocking pattern as `run-detail-answer.spec.ts`: `GET /api/runs/{id}/detail` and
 * `POST /api/runs/{id}/signals` mocked with `page.route()`.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939d1';
const URL = `/workflows/${RUN_ID}`;

const BUILD = 'epics[0].stories[0].build';
const SESSION_ID = 'ses_abc123';
const INSTRUCTION = 'fix the enum mapping';

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'needs_you',
    admitted_signals: ['retry', 'cancel'],
    branch: 'feat/step-handling-1',
    budget_usd: '40.00',
    compare_urls: [],
    created_at: '2026-09-07T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: null,
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '5.00',
    template: 'epic',
    terminal_session: false,
    version: 1,
    worktree_path: null,
    worktrees: [],
    accepted_paths: [],
    ...overrides,
  };
}

function detail(
  replyAvailable: boolean,
  resumeUnavailableReason: string | null,
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
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
    alert: {
      token: 'ERR',
      reason: 'exit 1',
      park_kind: 'agent_error',
      row_kind: 'agent',
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
        latest: {
          session_id: replyAvailable ? SESSION_ID : null,
        },
      },
    ],
    stories: [{ epic_index: 1, story_id: '1-1', state: 'current', cost_usd: '5.00' }],
    cost: {
      spent_usd: '5.00',
      budget_usd: '40.00',
      tokens_in: 10000,
      tokens_out: 3000,
      wall_clock_seconds: 600,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: ['retry', 'cancel'],
    reply_available: replyAvailable,
    resume_unavailable_reason: resumeUnavailableReason,
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

async function open(page: Page, body: Record<string, unknown>): Promise<void> {
  await mockDetail(page, body);
  await page.goto(URL);
  await expect(page.getByTestId('wf-header')).toBeVisible();
}

test.describe('RetryBox', () => {
  test('renders when retry is admitted, regardless of replyAvailable=false', async ({ page }) => {
    await open(page, detail(false, 'no_session'));

    await expect(page.getByTestId('wf-retry-box')).toBeVisible();
    await expect(page.getByTestId('wf-signal-retry')).toBeVisible();
  });

  test('renders when retry is admitted with replyAvailable=true', async ({ page }) => {
    await open(page, detail(true, null));

    await expect(page.getByTestId('wf-retry-box')).toBeVisible();
    await expect(page.getByTestId('wf-signal-retry')).toBeVisible();
  });

  test('session radio is checked by default when replyAvailable=true', async ({ page }) => {
    await open(page, detail(true, null));

    const sessionRadio = page.locator('input[type="radio"][value="session"]');
    await expect(sessionRadio).toBeChecked();
    const restartRadio = page.locator('input[type="radio"][value="restart"]');
    await expect(restartRadio).not.toBeChecked();
  });

  test('restart radio is checked by default when replyAvailable=false', async ({ page }) => {
    await open(page, detail(false, 'no_session'));

    const restartRadio = page.locator('input[type="radio"][value="restart"]');
    await expect(restartRadio).toBeChecked();
    // No session radio rendered
    await expect(page.locator('input[type="radio"][value="session"]')).toHaveCount(0);
  });

  test('no_session reason states no session was recorded', async ({ page }) => {
    await open(page, detail(false, 'no_session'));

    await expect(page.locator('.wf-retry-unavailable')).toContainText(
      'No session was recorded for this stop; restart is the only path.',
    );
  });

  test('no_capability reason states the harness does not support resume', async ({ page }) => {
    await open(page, detail(false, 'no_capability'));

    await expect(page.locator('.wf-retry-unavailable')).toContainText(
      'This harness does not support resume; restart is the only path.',
    );
  });

  test('text field accepts input and posts it with the signal', async ({ page }) => {
    await open(page, detail(true, null));

    const posted: Record<string, unknown>[] = [];
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      posted.push(route.request().postDataJSON() as Record<string, unknown>);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(run({ status: 'running' })),
      });
    });

    await page.getByTestId('wf-retry-instruction').fill(INSTRUCTION);
    await page.getByTestId('wf-signal-retry').click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].kind).toBe('retry');
    const payload = posted[0].payload as Record<string, unknown>;
    expect(payload.mode).toBe('session');
    expect(payload.text).toBe(INSTRUCTION);
  });

  test('posting restart mode sends mode:restart', async ({ page }) => {
    await open(page, detail(true, null));

    const posted: Record<string, unknown>[] = [];
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      posted.push(route.request().postDataJSON() as Record<string, unknown>);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(run({ status: 'running' })),
      });
    });

    await page.locator('input[type="radio"][value="restart"]').click();
    await page.getByTestId('wf-signal-retry').click();

    await expect.poll(() => posted.length).toBe(1);
    const payload = posted[0].payload as Record<string, unknown>;
    expect(payload.mode).toBe('restart');
  });

  test('text omitted from payload when field is empty', async ({ page }) => {
    await open(page, detail(true, null));

    const posted: Record<string, unknown>[] = [];
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      posted.push(route.request().postDataJSON() as Record<string, unknown>);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(run({ status: 'running' })),
      });
    });

    // leave text field empty
    await page.getByTestId('wf-signal-retry').click();

    await expect.poll(() => posted.length).toBe(1);
    const payload = posted[0].payload as Record<string, unknown>;
    expect(payload).not.toHaveProperty('text');
  });
});
