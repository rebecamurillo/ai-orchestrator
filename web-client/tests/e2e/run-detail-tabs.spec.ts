import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * The Run detail's tabbed region (story 1-4): GATE, STEPS, and SESSION when there is one.
 *
 * Story 1-4 moved the Steps table out of the page body and into one panel of three. That is a
 * product decision, and it is the one this module states — but it also moved a row that other
 * reads *link to*: `runs-history.spec.ts` arrives at `/workflows/{id}#step-{seq}` expecting the
 * named row promoted and in view, and a row inside an unopened panel is not rendered at all,
 * so the arrival scrolled to nothing and landed on the gate record (FR-25's own link rule).
 * The last test here is that regression's guard: the fragment opens STEPS, and it does so even
 * on a Run whose terminal would otherwise claim the default.
 *
 * `run-detail.spec.ts` and `run-detail-story-additions.spec.ts` read rows through this region
 * under the same operator revision (2026-09-18); what each row *says* stays theirs.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939aa';
const URL = `/workflows/${RUN_ID}`;
const COMMAND = 'cd /work/orchestrator && claude --resume sess-1';

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'running',
    admitted_signals: [],
    branch: 'epics/1',
    budget_usd: '15.00',
    compare_urls: [],
    created_at: '2026-09-07T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: null,
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '4.18',
    template: 'initiative',
    terminal_session: false,
    version: 1,
    worktree_path: null,
    worktrees: [],
    accepted_paths: [],
    ...overrides,
  };
}

function stepRow(seq: number): Record<string, unknown> {
  return {
    seq,
    path: `row-${seq}`,
    label: `row-${seq}`,
    kind: 'shell',
    gate: 'deterministic',
    status: 'planned',
    token: 'QUE',
    reason: null,
    attempts: 1,
    latest: null,
  };
}

function detail(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    header: {
      meta: {
        project: 'Mixed Signals',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'docs/initiative',
        template: 'initiative',
        version: 1,
        harness: 'claude',
        started_at: '2026-09-07T09:00:05Z',
        worktree_path: '/work/orchestrator',
      },
    },
    alert: null,
    steps: Array.from({ length: 8 }, (_, at) => stepRow(at + 1)),
    stories: [],
    cost: {
      spent_usd: '4.18',
      budget_usd: '15.00',
      tokens_in: 1000,
      tokens_out: 2000,
      wall_clock_seconds: 90,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: [],
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

const withTerminal = () =>
  detail({
    run: {
      terminal: { command: COMMAND, session_lifetime_ends_at: null, in_progress: false },
    },
  });

test.describe('/workflows/[id] (Run detail) — the tabbed region', () => {
  test('opens on GATE, and the Steps table is not rendered until STEPS is chosen', async ({
    page,
  }) => {
    await mockDetail(page, detail());
    await page.goto(URL);

    await expect(page.getByTestId('wf-header')).toBeVisible();
    await expect(page.getByRole('button', { name: 'GATE' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.getByTestId('wf-steps')).toHaveCount(0);

    await page.getByRole('button', { name: 'STEPS' }).click();

    await expect(page.getByTestId('wf-steps')).toBeVisible();
    await expect(page.getByTestId('wf-step-1')).toContainText('row-1');
  });

  test('a Run with no session offers no SESSION tab', async ({ page }) => {
    await mockDetail(page, detail());
    await page.goto(URL);

    await expect(page.getByTestId('wf-header')).toBeVisible();
    await expect(page.getByRole('button', { name: 'SESSION' })).toHaveCount(0);
  });

  test('a Run with a session opens on SESSION instead', async ({ page }) => {
    await mockDetail(page, withTerminal());
    await page.goto(URL);

    await expect(page.getByTestId('wf-header')).toBeVisible();
    await expect(page.getByRole('button', { name: 'SESSION' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  test('a #step-{seq} arrival opens STEPS and promotes the row it names', async ({ page }) => {
    await mockDetail(page, detail());
    await page.goto(`${URL}#step-6`);

    await expect(page.getByTestId('wf-header')).toBeVisible();
    await expect(page.getByRole('button', { name: 'STEPS' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.getByTestId('wf-step-6')).toHaveAttribute('data-anchored', 'true');
    await expect(page.getByTestId('wf-step-6')).toBeInViewport();
  });

  test('the arrival wins over the session default', async ({ page }) => {
    // A Run can have both; the Operator who followed a link to one row asked for that row.
    await mockDetail(page, withTerminal());
    await page.goto(`${URL}#step-6`);

    await expect(page.getByTestId('wf-header')).toBeVisible();
    await expect(page.getByTestId('wf-step-6')).toHaveAttribute('data-anchored', 'true');
  });
});
