import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * *Skip story* and its inline confirm in a real browser (6.4, FR-20, NFR-8, UX-DR10).
 *
 * The confirm is the half no unit test can reach: `vitest.config.ts` runs in
 * `environment: 'node'` with no DOM-mounting library, so `run-confirm-action.test.ts` asserts
 * only the closed render. Everything below is about what a click does — the line appearing,
 * *Skip story* posting exactly one signal, *Keep* posting none — plus the compare line on a
 * `done` Run, which is markup a click never touches but which belongs with the same feature.
 *
 * New file, for the reason `run-detail-answer.spec.ts` gives: the specs before it are frozen
 * and predate this control. `GET /api/runs/{id}/detail` and `POST /api/runs/{id}/signals`
 * are mocked with `page.route()` — there is no engine here to park a real Story, and every
 * assertion is about what the screen does with a given response.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939cd';
const URL = `/workflows/${RUN_ID}`;

const STORY_ID = '4-3';
const VERIFY = 'epics[0].stories[2].verify';
const COMPARE = 'https://github.com/o/r/compare/main...epics/1';

const CONFIRM_LINE =
  'skip story 4-3: its remaining steps are marked skipped, the quality gate re-runs, ' +
  'leftovers are committed as "story 4-3: skipped by operator"';

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'needs_you',
    admitted_signals: ['retry', 'skip_story', 'skip_epic', 'cancel'],
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
      token: 'BLK',
      reason: 'verify failed 2/2',
      park_kind: 'verify_failed',
      row_kind: 'shell',
    },
    steps: [
      {
        seq: 1,
        path: VERIFY,
        label: 'verify',
        kind: 'shell',
        gate: 'deterministic',
        status: 'error',
        token: 'ERR',
        reason: 'exit 1',
        attempts: 2,
        latest: null,
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
    admitted_signals: ['retry', 'skip_story', 'skip_epic', 'cancel'],
    summary: null,
    ...overrides,
    run: run((overrides.run as Record<string, unknown>) ?? {}),
  };
}

async function mockDetail(page: Page, body: Record<string, unknown>): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/detail`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

async function open(page: Page, body = detail()): Promise<void> {
  await mockDetail(page, body);
  await page.goto(URL);
  await expect(page.getByTestId('wf-header')).toBeVisible();
}

test.describe('Skip story', () => {
  test('a verify_failed stop offers it, and clicking states what it will do', async ({ page }) => {
    await open(page);

    await expect(page.getByTestId('wf-confirm-skip_story')).toHaveCount(0);
    await page.getByTestId('wf-signal-skip_story').click();

    await expect(page.getByTestId('wf-confirm-skip_story-line')).toHaveText(CONFIRM_LINE);
    await expect(page.getByTestId('wf-confirm-skip_story-yes')).toBeVisible();
    await expect(page.getByTestId('wf-confirm-skip_story-keep')).toBeVisible();
  });

  test('confirming posts the signal once and re-fetches', async ({ page }) => {
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

    await page.getByTestId('wf-signal-skip_story').click();
    await page.getByTestId('wf-confirm-skip_story-yes').click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].kind).toBe('skip_story');
    await expect(page.getByTestId('wf-stop-verify_failed')).toHaveCount(0);
  });

  test('Keep posts nothing and puts the button back', async ({ page }) => {
    await open(page);

    let calls = 0;
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      calls += 1;
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.getByTestId('wf-signal-skip_story').click();
    await page.getByTestId('wf-confirm-skip_story-keep').click();

    await expect(page.getByTestId('wf-signal-skip_story')).toBeVisible();
    await expect(page.getByTestId('wf-confirm-skip_story')).toHaveCount(0);
    expect(calls).toBe(0);
  });

  test('the re-baseline park withdraws it and keeps Retry', async ({ page }) => {
    await open(
      page,
      detail({
        alert: {
          token: 'BLK',
          reason: 're-baseline failed after skip',
          park_kind: 'verify_failed',
          row_kind: 'shell',
        },
        admitted_signals: ['retry', 'skip_epic', 'cancel'],
        run: { admitted_signals: ['retry', 'skip_epic', 'cancel'] },
      }),
    );

    await expect(page.getByTestId('wf-signal-skip_story')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-retry')).toBeVisible();
    await expect(page.getByTestId('wf-cancel')).toBeVisible();
  });

  test('a done Run names the skipped story beside the compare link', async ({ page }) => {
    await open(
      page,
      detail({
        alert: null,
        admitted_signals: [],
        summary: {
          progress: {
            epics_done: 1,
            epics_total: 1,
            stories_done: 3,
            stories_total: 3,
            links: 1,
          },
          links: [COMPARE],
          skipped: [STORY_ID],
        },
        run: { status: 'done', admitted_signals: [], compare_urls: [COMPARE] },
      }),
    );

    await expect(page.getByTestId('wf-cost')).toContainText(`${COMPARE} · skipped: ${STORY_ID}`);
  });
});
