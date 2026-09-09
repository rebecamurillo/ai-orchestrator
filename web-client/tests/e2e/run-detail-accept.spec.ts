import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * *Raise budget* and *Accept changes* in a real browser (6.6, FR-17, FR-31, UX-DR10).
 *
 * Both controls carry a payload, and typing into one of them is the half no unit test can
 * reach: `vitest.config.ts` runs in `environment: 'node'` with no DOM-mounting library, so
 * `run-budget-raise-box.test.ts` asserts only the first render. Everything below is about
 * what a click posts — the figure that was typed, and the file list exactly as the park
 * recorded it.
 *
 * New file, for the reason `run-detail-skip-story.spec.ts` gives: the specs before it are
 * frozen and predate these two stops. `GET /api/runs/{id}/detail` and
 * `POST /api/runs/{id}/signals` are mocked with `page.route()` — there is no engine here to
 * park a real Run over budget, and every assertion is about what the screen does with a
 * given response. The budget park's own end-to-end proof is
 * `backend-api/tests/e2e/test_budget_raise.py`, on the real stack.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939ce';
const URL = `/workflows/${RUN_ID}`;

const STORY_ID = '4-1';
const BUILD = 'epics[0].stories[0].build';
const TEST_FILE = 'tests/api/test_runs.py';
const AGENTS = 'AGENTS.md';

const ACCEPT_LINE =
  'Accept records these files as accepted for story 4-1; ' +
  'the check resumes on the same tree and the files ship with the story';

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'needs_you',
    admitted_signals: ['budget_raise', 'cancel'],
    branch: 'epics/1',
    budget_usd: '40.00',
    compare_urls: [],
    created_at: '2026-09-07T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: null,
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '41.20',
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
      reason: 'budget $41.20 / $40.00',
      park_kind: 'budget',
      row_kind: 'agent',
      payload: {},
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
        reason: 'intent gap',
        attempts: 1,
        latest: null,
      },
    ],
    stories: [{ epic_index: 0, story_id: STORY_ID, state: 'current', cost_usd: '41.20' }],
    cost: {
      spent_usd: '41.20',
      budget_usd: '40.00',
      tokens_in: 15000,
      tokens_out: 4200,
      wall_clock_seconds: 930,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: ['budget_raise', 'cancel'],
    summary: null,
    ...overrides,
    run: run((overrides.run as Record<string, unknown>) ?? {}),
  };
}

function protectedPathDetail(): Record<string, unknown> {
  return detail({
    alert: {
      token: 'BLK',
      reason: `protected path modified: ${TEST_FILE}, ${AGENTS}`,
      park_kind: 'protected_path',
      row_kind: 'agent',
      payload: {
        hits: [
          { path: TEST_FILE, kind: 'modified' },
          { path: AGENTS, kind: 'added' },
        ],
      },
    },
    admitted_signals: ['continue', 'retry', 'skip_story', 'skip_epic', 'cancel'],
    run: { admitted_signals: ['continue', 'retry', 'skip_story', 'skip_epic', 'cancel'] },
  });
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

function collect(page: Page, answer: Record<string, unknown>): Record<string, unknown>[] {
  const posted: Record<string, unknown>[] = [];
  void page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
    posted.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(answer),
    });
  });
  return posted;
}

test.describe('Raise budget', () => {
  test('the budget stop shows the cost and a field that already clears the spend', async ({
    page,
  }) => {
    await open(page);

    await expect(page.getByTestId('wf-stop-budget')).toContainText('budget $41.20 / $40.00');
    await expect(page.getByTestId('wf-budget-cost')).toContainText('$41.20 / $40.00');
    await expect(page.getByTestId('wf-budget-raise-input')).toHaveValue('52.00');
  });

  test('it offers no skip, because AD-13 admits none on this park', async ({ page }) => {
    await open(page);

    await expect(page.getByTestId('wf-signal-skip_story')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-skip_epic')).toHaveCount(0);
    await expect(page.getByTestId('wf-cancel')).toBeVisible();
  });

  test('raising posts the figure that was typed', async ({ page }) => {
    await open(page);
    const posted = collect(page, run({ status: 'running' }));

    await page.getByTestId('wf-budget-raise-input').fill('75.50');
    await page.getByTestId('wf-budget-raise').click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({ kind: 'budget_raise', payload: { budget_usd: '75.50' } });
  });

  test("a refused raise shows the server's own sentence and leaves the stop up", async ({
    page,
  }) => {
    await open(page);
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) =>
      route.fulfill({
        status: 409,
        contentType: 'application/problem+json',
        body: JSON.stringify({
          status: 409,
          title: 'Conflict',
          type: 'about:blank',
          detail: 'new budget must exceed spend $41.20',
        }),
      }),
    );

    await page.getByTestId('wf-budget-raise-input').fill('30');
    await page.getByTestId('wf-budget-raise').click();

    await expect(page.getByTestId('wf-budget-error')).toHaveText(
      'new budget must exceed spend $41.20',
    );
    await expect(page.getByTestId('wf-stop-budget')).toBeVisible();
  });
});

test.describe('Accept a protected-path change', () => {
  test('every file the park recorded is listed with its mark and a diff link', async ({ page }) => {
    await open(page, protectedPathDetail());

    await expect(page.getByTestId(`wf-accept-file-${TEST_FILE}`)).toContainText('~');
    await expect(page.getByTestId(`wf-accept-file-${AGENTS}`)).toContainText('+');
    await expect(page.getByTestId(`wf-accept-diff-${AGENTS}`)).toHaveAttribute(
      'href',
      `/api/runs/${RUN_ID}/files?path=AGENTS.md&diff=1`,
    );
  });

  test('the line names what accepting does before the button that does it', async ({ page }) => {
    await open(page, protectedPathDetail());

    await expect(page.getByTestId('wf-accept-line')).toHaveText(ACCEPT_LINE);
  });

  test('accepting posts continue with exactly the files the park recorded', async ({ page }) => {
    await open(page, protectedPathDetail());
    const posted = collect(page, run({ status: 'running' }));

    await page.getByTestId('wf-accept').click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({
      kind: 'continue',
      payload: { files: [TEST_FILE, AGENTS] },
    });
  });

  test('the plain Continue button is gone, and the other actions are not', async ({ page }) => {
    await open(page, protectedPathDetail());

    await expect(page.getByTestId('wf-signal-continue')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-retry')).toBeVisible();
    await expect(page.getByTestId('wf-signal-skip_story')).toBeVisible();
    await expect(page.getByTestId('wf-cancel')).toBeVisible();
  });
});
