import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * *Skip epic* and its inline confirm in a real browser (6.5, FR-20, NFR-8, UX-DR10),
 * including the `push_rejected` variant `run-detail-skip-story.spec.ts` (6.4) has no
 * equivalent of — Skip story is never offered there, Skip epic is the one control that adds
 * its own confirm sentence for it.
 *
 * Same mocking pattern as `run-detail-skip-story.spec.ts`: `GET /api/runs/{id}/detail` and
 * `POST /api/runs/{id}/signals` are mocked with `page.route()`, no compose stack or engine.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939ce';
const URL = `/workflows/${RUN_ID}`;

const PUSH = 'epics[0].push';

const ORDINARY_CONFIRM_LINE =
  'skip epic 1: remaining stories are marked skipped, the quality gate re-runs, ' +
  'done work is pushed and the compare link recorded';

const REJECTED_CONFIRM_LINE =
  'skip epic 1: remaining stories are marked skipped, the quality gate re-runs, ' +
  'the push is skipped';

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'needs_you',
    admitted_signals: ['retry', 'skip_epic', 'cancel'],
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
        project: 'Mixed Signals',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'specs/gates',
        template: 'initiative',
        version: 1,
        harness: 'fake',
        started_at: '2026-09-07T09:00:05Z',
        worktree_path: '/work/orchestrator',
      },
    },
    alert: {
      token: 'BLK',
      reason: 'the remote rejected it',
      park_kind: 'push_rejected',
      row_kind: 'git.push',
    },
    steps: [
      {
        seq: 1,
        path: PUSH,
        label: 'push',
        kind: 'git.push',
        gate: 'deterministic',
        status: 'error',
        token: 'ERR',
        reason: 'rejected',
        attempts: 1,
        latest: null,
      },
    ],
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
    gate_record: [
      {
        id: '33333333-3333-3333-3333-333333333333',
        at: '2026-09-07T09:10:00Z',
        path: PUSH,
        event: 'push_rejected',
        actor: 'machine',
        text: 'the remote rejected it',
        attempt_n: null,
      },
    ],
    admitted_signals: ['retry', 'skip_epic', 'cancel'],
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

test.describe('Skip epic', () => {
  test('a push_rejected stop offers it, with the push_rejected confirm sentence', async ({
    page,
  }) => {
    await open(page);

    await expect(page.getByTestId('wf-confirm-skip_epic')).toHaveCount(0);
    await page.getByTestId('wf-signal-skip_epic').click();

    await expect(page.getByTestId('wf-confirm-skip_epic-line')).toHaveText(REJECTED_CONFIRM_LINE);
    await expect(page.getByTestId('wf-confirm-skip_epic-yes')).toBeVisible();
    await expect(page.getByTestId('wf-confirm-skip_epic-keep')).toBeVisible();
  });

  test('an ordinary stop states the tail where done work still ships', async ({ page }) => {
    await open(
      page,
      detail({
        alert: { token: 'BLK', reason: 'verify failed 2/2', park_kind: 'verify_failed' },
        gate_record: [
          {
            id: '44444444-4444-4444-4444-444444444444',
            at: '2026-09-07T09:10:00Z',
            path: 'epics[0].stories[1].verify',
            event: 'verify_failed',
            actor: 'machine',
            text: 'verify failed 2/2',
            attempt_n: null,
          },
        ],
      }),
    );

    await page.getByTestId('wf-signal-skip_epic').click();

    await expect(page.getByTestId('wf-confirm-skip_epic-line')).toHaveText(ORDINARY_CONFIRM_LINE);
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

    await page.getByTestId('wf-signal-skip_epic').click();
    await page.getByTestId('wf-confirm-skip_epic-yes').click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].kind).toBe('skip_epic');
    await expect(page.getByTestId('wf-stop-push_rejected')).toHaveCount(0);
  });

  test('Keep posts nothing and puts the button back', async ({ page }) => {
    await open(page);

    let calls = 0;
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      calls += 1;
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.getByTestId('wf-signal-skip_epic').click();
    await page.getByTestId('wf-confirm-skip_epic-keep').click();

    await expect(page.getByTestId('wf-signal-skip_epic')).toBeVisible();
    await expect(page.getByTestId('wf-confirm-skip_epic')).toHaveCount(0);
    expect(calls).toBe(0);
  });

  test('a done Run names the epics it gave up the push on, beside the stories skipped', async ({
    page,
  }) => {
    await open(
      page,
      detail({
        alert: null,
        admitted_signals: [],
        summary: {
          progress: {
            epics_done: 2,
            epics_total: 2,
            stories_done: 3,
            stories_total: 4,
            links: 1,
          },
          links: ['https://github.com/o/r/compare/main...epics/1'],
          skipped: ['4-2'],
          skipped_epics: [1],
        },
        run: { status: 'done', admitted_signals: [] },
      }),
    );

    await expect(page.getByTestId('wf-summary')).toContainText('epics skipped: 1');
  });
});
