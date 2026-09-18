import { expect, test, type Page, type Route } from '@playwright/test';

import { MIXED_ID } from './projects-fixtures.mjs';

/**
 * Board LIST view (story 8-4).
 *
 * `GET /api/v1/projects` answers unconditionally empty in the shared stub, so every spec
 * here opens with `?project=` — the same deep-link resolution `board.spec.ts` documents in
 * its own module comment. The board API request is mocked with `page.route()`.
 */

const BOARD_URL = `/?project=${MIXED_ID}`;

const AMBER = 'rgb(228, 179, 60)';

const EMPTY_COLUMNS = { queued: [], running: [], needs_you: [], done: [], failed: [] };

type CardOverrides = Record<string, unknown>;

function card(overrides: CardOverrides = {}): Record<string, unknown> {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    token: 'RUN',
    status: 'running',
    park_kind: null,
    branch: 'epics/1',
    project_name: 'Mixed Signals',
    repository_slug: 'orchestrator',
    current_step_label: 'epic 1 · story 3-2 · build',
    harness: null,
    template: 'initiative',
    version: 1,
    progress: { epics_done: 1, epics_total: 2, stories_done: 5, stories_total: 8, links: 1 },
    kind_label: null,
    age_seconds: 60,
    needs_you_since: null,
    ...overrides,
  };
}

function boardResponse(overrides: CardOverrides = {}): Record<string, unknown> {
  return {
    columns: EMPTY_COLUMNS,
    counts: { queued: 0, running: 0, needs_you: 0 },
    generated_at: new Date().toISOString(),
    ...overrides,
  };
}

async function mockBoard(page: Page, body: unknown): Promise<void> {
  await page.route('**/api/runs?view=board*', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

/** Re-definition of the `unexpectedSignals` helper from `board.spec.ts` (frozen) — same
 * logic, adapted for use in this spec. */
async function unexpectedSignals(
  page: Page,
  allowedRoots: string[] = [],
): Promise<{ selector: string; value: string }[]> {
  return page.evaluate((allowed: string[]) => {
    const AMBER_C = 'rgb(228, 179, 60)';
    const RED_C = 'rgb(224, 82, 82)';
    const found: { selector: string; value: string }[] = [];
    for (const element of document.querySelectorAll('*')) {
      const style = getComputedStyle(element);
      for (const property of ['color', 'background-color', 'border-left-color']) {
        const value = style.getPropertyValue(property);
        if (!value.includes(AMBER_C) && !value.includes(RED_C)) continue;
        if (allowed.some((selector) => element.closest(selector) !== null)) continue;
        const id = element.getAttribute('data-testid');
        const cls = element.getAttribute('class');
        found.push({
          selector:
            `${element.tagName.toLowerCase()}` +
            `${cls ? `.${cls.split(/\s+/).join('.')}` : ''}` +
            `${id ? `[data-testid=${id}]` : ''}`,
          value,
        });
      }
    }
    return found;
  }, allowedRoots);
}

test.describe('/ (Board — LIST view)', () => {
  test('LIST selected: rows appear grouped in order, 7 fields per row, URL updates, no extra API request; BOARD restores columns', async ({
    page,
  }) => {
    let boardRequestCount = 0;
    const body = boardResponse({
      columns: {
        queued: [card({ id: 'q1', token: 'QUE', status: 'queued' })],
        running: [card({ id: 'r1', token: 'RUN', status: 'running' })],
        needs_you: [card({ id: 'n1', token: 'BLK', status: 'needs_you' })],
        done: [card({ id: 'd1', token: 'DON', status: 'done' })],
        failed: [card({ id: 'f1', token: 'ERR', status: 'failed' })],
      },
      counts: { queued: 1, running: 1, needs_you: 1 },
    });

    await page.route('**/api/runs?view=board*', (route: Route) => {
      boardRequestCount++;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });

    await page.goto(BOARD_URL);
    // wait for the initial board render with real card data
    await expect(page.getByTestId('board-card-r1')).toBeVisible();
    const countAfterLoad = boardRequestCount;

    // toggle to list — no navigation, no new request
    await page.getByTestId('board-toggle-list').click();

    await expect(page.getByTestId('board-list')).toBeVisible();

    // groups appear in the spec-mandated order (text-transform: uppercase in CSS)
    const heads = await page.locator('.board-list-group-head').allInnerTexts();
    expect(heads).toEqual(['NEEDS YOU', 'RUNNING', 'QUEUED', 'DONE', 'FAILED']);

    // all 7 text fields for a known row
    const knownRow = page.getByTestId('board-list-row-r1');
    await expect(knownRow).toContainText('RUN');
    await expect(knownRow).toContainText('Mixed Signals');
    await expect(knownRow).toContainText('orchestrator');
    await expect(knownRow).toContainText('epics/1');
    await expect(knownRow).toContainText('epic 1 · story 3-2 · build');
    await expect(knownRow).toContainText('1/2 epics');
    await expect(knownRow).toContainText('1m');

    // URL carries ?view=list
    await expect(page).toHaveURL(/[?&]view=list/);

    // no extra board request was made during the toggle
    expect(boardRequestCount).toBe(countAfterLoad);

    // click BOARD to restore columns
    await page.getByTestId('board-toggle-view').getByRole('button', { name: 'BOARD' }).click();

    await expect(page.getByTestId('board-column-queued')).toBeVisible();
    await expect(page.locator('[data-testid="board-list"]')).toHaveCount(0);
    // URL no longer carries ?view=list
    await expect(page).not.toHaveURL(/[?&]view=list/);
    // still no extra request
    expect(boardRequestCount).toBe(countAfterLoad);
  });

  test('reload with ?view=list: board-list is visible on mount without a toggle click', async ({
    page,
  }) => {
    await mockBoard(
      page,
      boardResponse({
        columns: { ...EMPTY_COLUMNS, running: [card({ id: 'r1' })] },
        counts: { queued: 0, running: 1, needs_you: 0 },
      }),
    );

    await page.goto(`${BOARD_URL}&view=list`);
    await expect(page.getByTestId('board-list')).toBeVisible();
  });

  test('BLK card aged ≥48h in list view: token cell and age cell are amber, nothing else outside the row is', async ({
    page,
  }) => {
    await mockBoard(
      page,
      boardResponse({
        columns: {
          ...EMPTY_COLUMNS,
          needs_you: [
            card({ id: 'n1', token: 'BLK', status: 'needs_you', age_seconds: 49 * 3600 }),
          ],
        },
        counts: { queued: 0, running: 0, needs_you: 1 },
      }),
    );

    await page.goto(`${BOARD_URL}&view=list`);
    await expect(page.getByTestId('board-list')).toBeVisible();

    const row = page.getByTestId('board-list-row-n1');
    await expect(row.locator('.board-list-token')).toHaveCSS('color', AMBER);
    await expect(row.locator('.board-list-age')).toHaveCSS('color', AMBER);

    // no amber outside the row and the nav badge (syncRail writes it for needs_you > 0)
    const signals = await unexpectedSignals(page, [
      '[data-testid="board-list-row-n1"]',
      '[data-testid="nav-needs-you"]',
    ]);
    expect(signals, JSON.stringify(signals)).toEqual([]);
  });

  test('rows within a group are sorted ascending age_seconds (youngest card first)', async ({
    page,
  }) => {
    await mockBoard(
      page,
      boardResponse({
        columns: {
          ...EMPTY_COLUMNS,
          running: [
            card({ id: 'old', token: 'RUN', status: 'running', age_seconds: 7200 }),
            card({ id: 'new', token: 'RUN', status: 'running', age_seconds: 120 }),
          ],
        },
        counts: { queued: 0, running: 2, needs_you: 0 },
      }),
    );

    await page.goto(`${BOARD_URL}&view=list`);
    await expect(page.getByTestId('board-list')).toBeVisible();

    const rows = page
      .locator('.board-list-group')
      .filter({ hasText: 'RUNNING' })
      .locator('[data-testid^="board-list-row-"]');
    // operator revision 2026-09-18: `board-list` is visible before the fetch answers (groups
    // render only once cards arrive), so the one-shot `evaluateAll` below raced the render on
    // slow machines. The retrying count waits for the rows; the order assertion is unchanged.
    await expect(rows).toHaveCount(2);
    const ids = await rows.evaluateAll((els) => els.map((el) => el.getAttribute('data-testid')));
    expect(ids).toEqual(['board-list-row-new', 'board-list-row-old']);
  });
});
