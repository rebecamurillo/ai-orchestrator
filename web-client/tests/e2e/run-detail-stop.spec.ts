import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * AD-24 in a real browser: the Run page names the stop it is answering, a draft never
 * outlives its stop, and a refusal shows the stop the Run has moved to.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939cc';
const URL = `/workflows/${RUN_ID}`;

const STORY_ID = '4-1';
const BUILD = 'epics[0].stories[0].build';
const ANSWER = "Post to the project's channel only";

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'needs_you',
    admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'],
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
        harness: 'claude',
        started_at: '2026-09-07T09:00:05Z',
        worktree_path: '/work/orchestrator',
      },
    },
    alert: {
      token: 'BLK',
      reason: '## Auto Run Result\n\nWhich channel should the notification post to?',
      park_kind: 'blocked',
      attribution: {
        harness: 'claude',
        model: 'claude-opus-4',
        ended_at: '2026-09-07T09:12:00Z',
      },
    },
    steps: [
      {
        seq: 1,
        path: BUILD,
        label: 'build',
        kind: 'agent',
        gate: 'liveness',
        status: 'blocked',
        token: 'BLK',
        reason: null,
        attempts: 1,
        latest: {
          n: 1,
          started_at: '2026-09-07T09:10:00Z',
          ended_at: '2026-09-07T09:12:00Z',
          seconds: 120,
          harness: 'claude',
          model: 'claude-opus-4',
          exit_code: 0,
          cost_usd: '3.20',
          log_tail: [],
        },
      },
    ],
    stories: [{ epic_index: 1, story_id: STORY_ID, state: 'current', cost_usd: '3.20' }],
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
    admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'],
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

async function open(page: Page): Promise<void> {
  await mockDetail(page, detail());
  await page.goto(URL);
  await expect(page.getByTestId('wf-header')).toBeVisible();
}

const STOP = 7;

function atStop(parkSeq: number, reason: string): Record<string, unknown> {
  const base = detail() as { run: Record<string, unknown>; alert: Record<string, unknown> };
  return detail({
    run: { ...base.run, park_seq: parkSeq },
    alert: { ...base.alert, reason },
  });
}

async function capture(page: Page): Promise<() => Record<string, unknown> | null> {
  let posted: Record<string, unknown> | null = null;
  await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
    posted = route.request().postDataJSON() as Record<string, unknown>;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(run({ status: 'running' })),
    });
  });
  return () => posted;
}

test.describe('the stop a signal answers', () => {
  test('an Answer names the stop it was written for', async ({ page }) => {
    await mockDetail(page, atStop(STOP, 'first question'));
    await page.goto(URL);
    await page.getByTestId('wf-answer').fill(ANSWER);
    const posted = await capture(page);

    await page.getByTestId('wf-signal-answer').click();

    await expect.poll(posted).not.toBeNull();
    expect(posted()!.stop).toBe(STOP);
  });

  test('a Run that has not stopped sends no number', async ({ page }) => {
    await open(page);
    await page.getByTestId('wf-answer').fill(ANSWER);
    const posted = await capture(page);

    await page.getByTestId('wf-signal-answer').click();

    await expect.poll(posted).not.toBeNull();
    expect(posted()).not.toHaveProperty('stop');
  });

  test('a refusal shows the stop the Run has moved to, and the old draft is gone', async ({
    page,
  }) => {
    await mockDetail(page, atStop(STOP, 'first question'));
    await page.goto(URL);
    await page.getByTestId('wf-answer').fill(ANSWER);

    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) =>
      route.fulfill({
        status: 409,
        contentType: 'application/problem+json',
        body: JSON.stringify({
          type: 'about:blank',
          title: 'conflict',
          status: 409,
          detail: `this signal names stop ${STOP}, and the Run is at stop ${STOP + 1}`,
        }),
      }),
    );
    await page.unroute(`**/api/runs/${RUN_ID}/detail**`);
    await mockDetail(page, atStop(STOP + 1, 'second question'));

    await page.getByTestId('wf-signal-answer').click();

    await expect(page.getByTestId('wf-question').getByText('second question')).toBeVisible();
    await expect(page.getByTestId('wf-answer')).toHaveValue('');
    await expect(page.getByTestId('wf-signal-error')).toContainText(`stop ${STOP + 1}`);
  });
});
