import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * The HISTORY row's *path* cell opens the step-run detail page (story 1-2).
 *
 * A row of the history is one attempt of one step, and since story 1-2 this system serves a
 * page for exactly that (`/workflows/{id}/steps/{path}`), so the cell naming the step links
 * there rather than into the Run detail's table. The *workflow* cell keeps `rowHref`'s
 * `#step-{seq}` arrival, and `runs-history.spec.ts` pins that it still scrolls and promotes —
 * the two cells answer two different questions, and this module is the one that moved.
 *
 * The path travels dot-index encoded (`lib/step-path.ts::encode`), because `epics[0]` in a
 * URL path segment is bracket text a server may normalise; `step-path.test.ts` settles the
 * encoding itself, and what only a browser can settle is that the href the table renders is
 * the URL the page is served at.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939aa';
const ATTEMPT_ID = '00000000-0000-0000-0000-000000000001';
const STEP_PATH = 'epics[0].stories[3].build';
const ENCODED_PATH = 'epics.0.stories.3.build';

function historyRow(): Record<string, unknown> {
  return {
    attempt_id: ATTEMPT_ID,
    run_id: RUN_ID,
    seq: 7,
    started_at: '2026-09-09T08:04:05Z',
    ended_at: '2026-09-09T08:06:35Z',
    seconds: 150,
    project_name: 'Mixed Signals',
    run_label: 'story v3 · feat/epic-7',
    path: STEP_PATH,
    kind: 'agent',
    harness: 'codex',
    model: 'gpt-5-codex',
    session_id: 'sess-1',
    status: 'done',
    token: 'DON',
    tokens_in: 100,
    tokens_out: 20,
    cost_usd: '0.250000',
    cost_provisional: false,
    trace_url: 'https://langfuse.test/traces/1',
    log_tail_url: `/api/v1/runs/${RUN_ID}/detail`,
  };
}

async function openHistory(page: Page): Promise<void> {
  await page.route('**/api/queue*', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ running: [], queued: [], updated_at: null }),
    }),
  );
  await page.route('**/api/steps*', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [historyRow()], next_cursor: null }),
    }),
  );
  await page.goto('/runs');
  await expect(page.getByTestId('runs-history')).toBeVisible();
}

test.describe('/runs (HISTORY section) — the path cell', () => {
  test('links to the step-run detail page, path-encoded', async ({ page }) => {
    await openHistory(page);

    const path = page
      .getByTestId(`runs-history-row-${ATTEMPT_ID}`)
      .getByRole('link', { name: STEP_PATH });

    await expect(path).toHaveAttribute('href', `/workflows/${RUN_ID}/steps/${ENCODED_PATH}`);
  });

  test('clicking it opens that step, not the Run detail', async ({ page }) => {
    await openHistory(page);

    await page
      .getByTestId(`runs-history-row-${ATTEMPT_ID}`)
      .getByRole('link', { name: STEP_PATH })
      .click();

    await expect(page).toHaveURL(
      new RegExp(`/workflows/${RUN_ID}/steps/${ENCODED_PATH.replace(/\./g, '\\.')}$`),
    );
  });
});
