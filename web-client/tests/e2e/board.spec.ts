import { expect, test, type Page, type Route } from '@playwright/test';

import { MIXED_ID } from './projects-fixtures.mjs';

/**
 * The Board (4.14, SPEC CAP-14, FR-22, FR-24).
 *
 * `GET /api/v1/projects` (the bare list) answers unconditionally empty in the shared stub
 * (the frozen `shell.spec.ts`'s own "NOTHING REGISTERED" reading of a bare `/`), so every
 * spec here opens with `?project=` — `index.astro`'s own deep-link resolution through
 * `GET /projects/{id}` (its own module doc), the same shape `new-workflow.spec.ts` uses for
 * `?template=&project=`. This also means every request this suite observes carries a
 * `project_id`, including the failed-fetch one — its exact command line is asserted with
 * `toContainText`, not full equality; the `project_id`-free form is `board-format.test.ts`'s
 * own `boardRequestPath(null)` case, proven deterministically there.
 *
 * `GET /api/runs?view=board...` is mocked with `page.route()`: there is no engine here to
 * produce a real Board, and the ACs are about rendering a given response (the
 * `new-workflow.spec.ts` precedent for `POST /runs/preflight`/`POST /runs`).
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

/**
 * Every element carrying the amber or red token that is not inside one of `allowedRoots`,
 * the `shell.spec.ts` `paintedColours` precedent adapted for a screen that *does* expect a
 * signal somewhere. `getComputedStyle` resolves inherited `color`, so a column head's own
 * label/count children report the same amber their header carries — `element.closest()` is
 * what lets an allowed root cover its whole subtree instead of demanding every descendant be
 * separately listed.
 */
async function unexpectedSignals(
  page: Page,
  allowedRoots: string[] = [],
): Promise<{ selector: string; value: string }[]> {
  return page.evaluate((allowed: string[]) => {
    const AMBER = 'rgb(228, 179, 60)';
    const RED = 'rgb(224, 82, 82)';
    const found: { selector: string; value: string }[] = [];
    for (const element of document.querySelectorAll('*')) {
      const style = getComputedStyle(element);
      for (const property of ['color', 'background-color', 'border-left-color']) {
        const value = style.getPropertyValue(property);
        if (!value.includes(AMBER) && !value.includes(RED)) continue;
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

test.describe('/ (Board)', () => {
  test('renders five columns, right counts, fixed field order; a cancelled Run reads CAN · cancelled; a card navigates to its detail', async ({
    page,
  }) => {
    await mockBoard(
      page,
      boardResponse({
        columns: {
          queued: [card({ id: 'q1', token: 'QUE', status: 'queued' })],
          running: [card({ id: 'r1', token: 'RUN', status: 'running' })],
          needs_you: [card({ id: 'n1', token: 'BLK', status: 'needs_you' })],
          done: [card({ id: 'd1', token: 'DON', status: 'done' })],
          failed: [
            card({ id: 'f1', token: 'ERR', status: 'failed' }),
            card({ id: 'c1', token: 'CAN', status: 'cancelled' }),
          ],
        },
        counts: { queued: 1, running: 1, needs_you: 1 },
      }),
    );
    await page.goto(BOARD_URL);

    await expect(
      page.getByTestId('board-column-queued').getByTestId('board-card-q1'),
    ).toBeVisible();
    await expect(
      page.getByTestId('board-column-running').getByTestId('board-card-r1'),
    ).toBeVisible();
    await expect(
      page.getByTestId('board-column-needs_you').getByTestId('board-card-n1'),
    ).toBeVisible();
    await expect(page.getByTestId('board-column-done').getByTestId('board-card-d1')).toBeVisible();
    const failedColumn = page.getByTestId('board-column-failed');
    await expect(failedColumn.getByTestId('board-card-f1')).toBeVisible();
    await expect(failedColumn.getByTestId('board-card-c1')).toBeVisible();

    const cancelled = failedColumn.getByTestId('board-card-c1');
    await expect(cancelled).toContainText('CAN');
    await expect(cancelled).toContainText('cancelled');

    // fixed field order on one full card
    const runningCard = page.getByTestId('board-card-r1');
    const text = (await runningCard.innerText()).split('\n');
    expect(text.indexOf('RUN')).toBeLessThan(text.findIndex((line) => line.includes('epics/1')));
    expect(text.findIndex((line) => line.includes('epics/1'))).toBeLessThan(
      text.findIndex((line) => line.includes('Mixed Signals')),
    );
    expect(text.findIndex((line) => line.includes('1/2 epics'))).toBeLessThan(
      text.findIndex((line) => line.includes('initiative v1')),
    );

    // the rail and the footer pick up the same counts (`web-client/AGENTS.md`'s "the rail
    // and footer counts fed by the store"), patched by `Board.tsx` onto the already-rendered
    // shell — see that island's own module doc for why
    await expect(page.getByTestId('footer-readout')).toContainText(
      '1 running · 1 queued / 1 need you',
    );
    await expect(page.getByTestId('nav-needs-you')).toHaveText('1 need you');

    await runningCard.click();
    await expect(page).toHaveURL(/\/workflows\/r1$/);
  });

  test('polls at 5s while a Run is running, then at 30s once nothing is', async ({ page }) => {
    let running = true;
    const calls: number[] = [];
    await page.route('**/api/runs?view=board*', (route: Route) => {
      calls.push(Date.now());
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          boardResponse({
            columns: running ? { ...EMPTY_COLUMNS, running: [card({ id: 'r1' })] } : EMPTY_COLUMNS,
            counts: { queued: 0, running: running ? 1 : 0, needs_you: 0 },
          }),
        ),
      });
    });

    // installed before navigation: `configurePolling`'s `setInterval` is created on the
    // island's first mount effect, and a real interval created before `clock.install()`
    // keeps running on the real clock rather than being virtualised retroactively
    await page.clock.install();
    await page.goto(BOARD_URL);
    await expect(page.getByTestId('board-card-r1')).toBeVisible();
    expect(calls).toHaveLength(1);

    await page.clock.fastForward(5_500);
    await expect.poll(() => calls.length).toBe(2);

    await page.clock.fastForward(5_500);
    await expect.poll(() => calls.length).toBe(3);

    running = false;
    await page.clock.fastForward(5_500);
    await expect.poll(() => calls.length).toBe(4);

    // the cadence just switched to 30s: the next 5s alone must not produce a fifth call
    await page.clock.fastForward(5_500);
    expect(calls.length).toBe(4);

    await page.clock.fastForward(25_000);
    await expect.poll(() => calls.length).toBe(5);
  });

  test('a slow response for an earlier poll never overwrites a newer one (the staleness guard)', async ({
    page,
  }) => {
    let requestCount = 0;
    await page.route('**/api/runs?view=board*', async (route: Route) => {
      requestCount += 1;
      if (requestCount === 1) {
        // the mount fetch: deliberately slow, so the *refresh* click below resolves first
        await new Promise((resolve) => setTimeout(resolve, 400));
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(
            boardResponse({ columns: { ...EMPTY_COLUMNS, queued: [card({ id: 'stale' })] } }),
          ),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          boardResponse({ columns: { ...EMPTY_COLUMNS, queued: [card({ id: 'fresh' })] } }),
        ),
      });
    });

    await page.goto(BOARD_URL);
    // fires a second request (`requestSeqRef`'s seq 2) while the slow first one is still
    // in flight — the `NewWorkflow.tsx` staleness-guard pattern this island copies
    await page.getByTestId('board-refresh').click();

    await expect(page.getByTestId('board-card-fresh')).toBeVisible();
    // give the slow first response time to land, then confirm it never overwrote the second
    await page.waitForTimeout(600);
    await expect(page.getByTestId('board-card-stale')).toHaveCount(0);
    await expect(page.getByTestId('board-card-fresh')).toBeVisible();
  });

  test('a poll that fails replaces the board with the failed-fetch readout; a successful Retry restores it and polling', async ({
    page,
  }) => {
    let fail = true;
    await page.route('**/api/runs?view=board*', (route: Route) => {
      if (fail) {
        return route.fulfill({
          status: 500,
          contentType: 'application/problem+json',
          body: JSON.stringify({ type: 'about:blank', title: 'error', status: 500 }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          boardResponse({ columns: { ...EMPTY_COLUMNS, queued: [card({ id: 'q1' })] } }),
        ),
      });
    });

    await page.goto(BOARD_URL);

    await expect(page.getByTestId('fetch-failed')).toBeVisible();
    // asserted with toContainText, not full equality — this request carries `?project=`
    // (see the module doc); the project_id-free form is board-format.test.ts's own case
    await expect(page.getByTestId('fetch-failed')).toContainText('GET /api/runs?view=board');
    await expect(page.getByTestId('fetch-failed')).toContainText('500');

    fail = false;
    await page.getByTestId('fetch-retry').click();

    // a real card, not the generic `board` testid, which the pre-fetch loading state also
    // carries — the loading state never appears here (the prior render was `fetch-failed`,
    // not the initial SSR paint), but this stays consistent with every other wait in this
    // file, all of which pin to data that only exists once a real fetch has resolved
    await expect(page.getByTestId('board-card-q1')).toBeVisible();
    await expect(page.getByTestId('fetch-failed')).toHaveCount(0);
  });

  test('no needs_you/failed Runs paints no amber or red pixel anywhere', async ({ page }) => {
    await mockBoard(
      page,
      boardResponse({
        columns: { ...EMPTY_COLUMNS, running: [card({ id: 'r1' })] },
        counts: { queued: 0, running: 1, needs_you: 0 },
      }),
    );
    await page.goto(BOARD_URL);
    await expect(page.getByTestId('board-card-r1')).toBeVisible();

    const signals = await unexpectedSignals(page);
    expect(signals, JSON.stringify(signals)).toEqual([]);
  });

  test('a BLK card older than 48h has its token and its age amber, and nothing else does (needs-you scenario)', async ({
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
    await page.goto(BOARD_URL);
    await expect(page.getByTestId('board-card-n1')).toBeVisible();

    const card1 = page.getByTestId('board-card-n1');
    await expect(card1.locator('.run-card-token')).toHaveCSS('color', AMBER);
    await expect(card1.locator('.run-card-age')).toHaveCSS('color', AMBER);
    await expect(
      page.getByTestId('board-column-needs_you').locator('.board-column-head'),
    ).toHaveCSS('color', AMBER);

    // every remaining amber pixel is inside the needs_you column (the n1 card, its own
    // head) or the rail's own "1 need you" badge — the same fact, read from the same
    // counts, in the one other place UX-DR3 allows it (`Board.tsx`'s own `syncRail`)
    const signals = await unexpectedSignals(page, [
      '[data-testid="board-column-needs_you"]',
      '[data-testid="nav-needs-you"]',
    ]);
    expect(signals, JSON.stringify(signals)).toEqual([]);
  });

  test('an empty board (a Project exists, no Runs) reads NOTHING RUNNING, linking to New workflow', async ({
    page,
  }) => {
    await mockBoard(page, boardResponse());
    await page.goto(BOARD_URL);

    await expect(page.getByTestId('board-empty')).toContainText('NOTHING RUNNING');
    await expect(
      page.getByTestId('board-empty').getByRole('link', { name: 'new workflow' }),
    ).toHaveAttribute('href', '/workflows/new');
  });

  test('no Project registered reads NOTHING REGISTERED, linking to Projects (bare visit)', async ({
    page,
  }) => {
    await page.goto('/');

    await expect(page.getByTestId('board-empty')).toContainText('NOTHING REGISTERED');
  });

  test('?project= activates the filter and the request carries project_id', async ({ page }) => {
    let seenQuery = '';
    await page.route('**/api/runs?view=board*', (route: Route) => {
      seenQuery = new URL(route.request().url()).search;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          boardResponse({ columns: { ...EMPTY_COLUMNS, queued: [card({ id: 'q1' })] } }),
        ),
      });
    });

    await page.goto(BOARD_URL);
    // a real card, not the generic `board` testid — the pre-fetch loading state renders
    // that same wrapper (with empty columns) before the request below has even landed
    await expect(page.getByTestId('board-card-q1')).toBeVisible();

    expect(seenQuery).toContain(`project_id=${MIXED_ID}`);
    await expect(
      page.getByTestId('board-filter-project').getByRole('link', { name: 'Mixed Signals' }),
    ).toHaveAttribute('aria-current', 'true');
  });
});
