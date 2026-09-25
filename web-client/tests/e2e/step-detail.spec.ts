import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * Step-run detail page — attempts table (CAP-6, story 5, 2026-09-25).
 *
 * Story 5 replaced the flex-wrap `<ul>` of dot-joined button labels with an HTML table
 * (`AttemptsTable`). The unit tests (`attempt-table.test.ts`) cover static rendering;
 * this spec covers what a browser shows: the header row, rows with correct columns,
 * selection by click, "prompt · result" and "reach agent" buttons, and the signal-coloured
 * token cell.
 *
 * The deferred note in story 5's review triage (medium severity, 2026-09-25) is what this
 * spec resolves: `onDrawer` routing was unverifiable from `renderToStaticMarkup`.
 *
 * `GET /api/runs/{runId}/steps/{stepPath}` is mocked with `page.route()` — there is no
 * engine here and every assertion is about what the screen does with a given response.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939d2';
// dot-index form for the URL; decode() → 'stories[0].build'
const DOT_PATH = 'stories.0.build';
const URL = `/workflows/${RUN_ID}/steps/${DOT_PATH}`;

const ATTEMPT_ID_1 = 'aaaaaaaa-0000-7000-a000-000000000001';
const ATTEMPT_ID_2 = 'aaaaaaaa-0000-7000-a000-000000000002';

function attempt(
  n: number,
  overrides: Partial<{
    id: string;
    status: string;
    token: string;
    harness: string;
    model: string;
    seconds: number;
    cost_usd: string;
    exit_code: number;
    command: string | null;
    resume_command: string | null;
  }> = {},
) {
  return {
    id: n === 1 ? ATTEMPT_ID_1 : ATTEMPT_ID_2,
    n,
    status: 'done',
    token: 'DON',
    started_at: '2026-09-25T10:00:00Z',
    ended_at: '2026-09-25T10:00:45Z',
    seconds: 45,
    harness: 'local',
    model: 'claude-sonnet-4-6',
    session_id: 'ses_abc',
    exit_code: 0,
    cost_usd: '0.42',
    cost_provisional: false,
    tokens_in: 8000,
    tokens_out: 2000,
    dispatch_prompt: 'Build the feature.',
    retry_prompt: null,
    result: 'Done.',
    command: null,
    resume_command: null,
    ...overrides,
  };
}

function stepDetail(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    seq: 1,
    path: 'stories[0].build',
    label: 'build',
    kind: 'agent',
    gate: 'liveness',
    status: 'done',
    token: 'DON',
    reason: null,
    with_resolved: { model: 'claude-sonnet-4-6' },
    attempts: [attempt(2), attempt(1)], // newest first
    ...overrides,
  };
}

async function mockStep(page: Page, body: Record<string, unknown>): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/steps/**`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

async function open(page: Page, body = stepDetail()): Promise<void> {
  await mockStep(page, body);
  await page.goto(URL);
  await expect(page.getByTestId('step-detail')).toBeVisible();
}

test.describe('Step detail — attempts table', () => {
  test('renders a table with the expected column headers', async ({ page }) => {
    await open(page);

    const table = page.locator('table.wf-step-attempts');
    await expect(table).toBeVisible();

    const headers = table.locator('th');
    const headerTexts = await headers.allTextContents();
    expect(headerTexts).toContain('#');
    expect(headerTexts).toContain('status');
    expect(headerTexts).toContain('harness');
    expect(headerTexts).toContain('model');
    expect(headerTexts).toContain('duration');
    expect(headerTexts).toContain('cost');
    expect(headerTexts).toContain('exit');
    expect(headerTexts).toContain('actions');
  });

  test('renders one row per attempt, newest (n=2) first', async ({ page }) => {
    await open(page);

    const rows = page.locator('table.wf-step-attempts tbody tr');
    await expect(rows).toHaveCount(2);

    const firstCells = await rows.first().locator('td').allTextContents();
    // First cell is attempt number; n=2 is newest and should appear first
    expect(firstCells[0]).toBe('2');

    const secondCells = await rows.last().locator('td').allTextContents();
    expect(secondCells[0]).toBe('1');
  });

  test('latest attempt (n=2) is pre-selected (data-selected=true)', async ({ page }) => {
    await open(page);

    const rows = page.locator('table.wf-step-attempts tbody tr');
    // First row (n=2) is the latest and pre-selected
    await expect(rows.first()).toHaveAttribute('data-selected', 'true');
    await expect(rows.last()).toHaveAttribute('data-selected', 'false');
  });

  test('clicking a row selects it', async ({ page }) => {
    await open(page);

    const rows = page.locator('table.wf-step-attempts tbody tr');
    await rows.last().click();

    await expect(rows.last()).toHaveAttribute('data-selected', 'true');
    await expect(rows.first()).toHaveAttribute('data-selected', 'false');
  });

  test('"prompt · result" button present for an agent step attempt', async ({ page }) => {
    await open(page);

    // n=2 row (first) — agent step, command=null
    await expect(page.getByTestId('step-prompt-2')).toBeVisible();
  });

  test('"reach agent" button present when resume_command is set', async ({ page }) => {
    await open(
      page,
      stepDetail({
        attempts: [
          attempt(1, {
            resume_command: 'cd /work/r/wt/x && opencode run --session ses_abc',
          }),
        ],
      }),
    );

    await expect(page.getByTestId('step-reach-1')).toBeVisible();
  });

  test('"reach agent" button absent when resume_command is null', async ({ page }) => {
    await open(page);

    await expect(page.getByTestId('step-reach-2')).toHaveCount(0);
    await expect(page.getByTestId('step-reach-1')).toHaveCount(0);
  });

  test('shell step has no "prompt · result" or "reach agent" button', async ({ page }) => {
    await open(
      page,
      stepDetail({
        kind: 'shell',
        attempts: [attempt(1, { command: 'make lint', resume_command: null })],
      }),
    );

    await expect(page.getByTestId('step-prompt-1')).toHaveCount(0);
    await expect(page.getByTestId('step-reach-1')).toHaveCount(0);
  });

  test('status token cell carries signal colour via data-signal attribute', async ({ page }) => {
    await open(
      page,
      stepDetail({
        status: 'error',
        token: 'ERR',
        attempts: [attempt(1, { status: 'error', token: 'ERR' })],
      }),
    );

    const tokenSpan = page.locator('table.wf-step-attempts .wf-step-token').first();
    await expect(tokenSpan).toBeVisible();
    // signal-coloured via data-signal attribute (NFR-6)
    const signal = await tokenSpan.getAttribute('data-signal');
    expect(signal).toBeTruthy();
  });

  test('clicking "prompt · result" opens the drawer', async ({ page }) => {
    await open(page);

    await page.getByTestId('step-prompt-2').click();

    // HelperDrawer (data-testid="step-drawer") should be visible after clicking
    await expect(page.getByTestId('step-drawer')).toBeVisible({ timeout: 3000 });
  });
});
