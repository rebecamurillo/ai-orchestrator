/**
 * The embedded run diagram — graph fetch error handling.
 *
 * 2026-09-24, v3: `?view=diagram` and its redirect are deleted, so the run detail is reached
 * at its own URL. Three cases: the failed request takes the diagram's place with its retry
 * control, a failing `/graph` is asked once rather than on every tick, and polling *resumes*
 * once the retry clears the error — the last of these because a suppression that never lifts
 * would freeze the diagram against a live Run and keep the other two green.
 *
 * The clock is faked (`run-activity.spec.ts`'s precedent): sleeping through two real 5 s poll
 * intervals makes the suite slow and the interval a number hard-coded in two places.
 */

import { expect, test, type Page, type Route } from '@playwright/test';

import { runDetail, STARTED_AT } from '../fixtures/run-detail';
import type { components } from '../../src/api/schema';

type RunGraphOut = components['schemas']['RunGraphOut'];

/** This spec's own Run, distinct from `run-diagram.spec.ts`'s. */
const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939ab';
const BASE_URL = `/workflows/${RUN_ID}`;
const NOW = new Date(Date.parse(STARTED_AT) + 60_000);
/** `$poll` ticks every 5 s while a Run is running (`stores/poll.ts`). */
const POLL_MS = 5_000;

function minimalDetail() {
  return runDetail([], { stories: [], run: { id: RUN_ID, branch: 'epics/8' } });
}

function minimalGraph(): RunGraphOut {
  return {
    nodes: [
      {
        id: 'root',
        kind: 'plan.check',
        label: 'root',
        gate: null,
        agent: false,
        human: false,
        call: null,
        status: 'running',
        token: 'RUN',
        current: true,
      },
    ],
    edges: [],
    groups: [],
  };
}

async function mockDetail(page: Page): Promise<void> {
  // the trailing `**` admits the `?opened=true` of the first fetch (story 8-3)
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(minimalDetail()),
    }),
  );
}

test.describe('/workflows/[id] — graph fetch error', () => {
  test('graph fetch error shows fetch-failed; retry re-calls /graph and clears the error', async ({
    page,
  }) => {
    let graphCallCount = 0;

    await mockDetail(page);
    await page.route(`**/api/runs/${RUN_ID}/graph`, async (route: Route) => {
      graphCallCount++;
      if (graphCallCount === 1) {
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'service unavailable' }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(minimalGraph()),
        });
      }
    });

    await page.clock.install({ time: NOW });
    await page.goto(BASE_URL);

    // Error state: FailedFetch rendered, wf-diagram absent
    await expect(page.locator('[data-testid="fetch-failed"]')).toBeVisible();
    await expect(page.locator('[data-testid="wf-diagram"]')).not.toBeVisible();
    expect(graphCallCount).toBe(1);

    // Click retry — handler calls fetchGraph (and fetchDetail) again
    await page.locator('[data-testid="fetch-retry"]').click();

    // Retry must have issued a second /graph request
    await expect(async () => {
      expect(graphCallCount).toBeGreaterThan(1);
    }).toPass({ timeout: 5000 });

    // Error cleared after successful retry, diagram visible
    await expect(page.locator('[data-testid="fetch-failed"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="wf-diagram"]')).toBeVisible({ timeout: 5000 });
  });

  test('asks a failing /graph once, not again on every poll tick', async ({ page }) => {
    // the island this replaced called `stopPolling()`, which is the *shared* loop the Run
    // detail runs on — stopping it took the whole surface's refresh down with the diagram's.
    // The section skips its own re-fetch while it is in the error phase instead, so the
    // readout cannot self-clear without the retry control being pressed.
    let graphCallCount = 0;

    await mockDetail(page);
    await page.route(`**/api/runs/${RUN_ID}/graph`, async (route: Route) => {
      graphCallCount++;
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'service unavailable' }),
      });
    });

    await page.clock.install({ time: NOW });
    await page.goto(BASE_URL);
    await expect(page.locator('[data-testid="fetch-failed"]')).toBeVisible();

    // the run is `running`, so the shared poll ticks; run through two of them
    await page.clock.runFor(POLL_MS * 2 + 500);

    expect(graphCallCount).toBe(1);
    await expect(page.locator('[data-testid="fetch-failed"]')).toBeVisible();
    await expect(page.locator('[data-testid="wf-diagram"]')).toHaveCount(0);
  });

  test('resumes polling once the retry has cleared the error', async ({ page }) => {
    // the suppression above must lift: a sticky guard would freeze the diagram against a
    // live Run for as long as the page is open, and pass both of the cases before this one
    let graphCallCount = 0;

    await mockDetail(page);
    await page.route(`**/api/runs/${RUN_ID}/graph`, async (route: Route) => {
      graphCallCount++;
      await route.fulfill(
        graphCallCount === 1
          ? {
              status: 503,
              contentType: 'application/json',
              body: JSON.stringify({ detail: 'service unavailable' }),
            }
          : {
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify(minimalGraph()),
            },
      );
    });

    await page.clock.install({ time: NOW });
    await page.goto(BASE_URL);
    await expect(page.locator('[data-testid="fetch-failed"]')).toBeVisible();

    await page.locator('[data-testid="fetch-retry"]').click();
    await expect(page.locator('[data-testid="wf-diagram"]')).toBeVisible();
    const afterRetry = graphCallCount;

    await page.clock.runFor(POLL_MS + 500);

    await expect.poll(() => graphCallCount).toBeGreaterThan(afterRetry);
    await expect(page.locator('[data-testid="fetch-failed"]')).toHaveCount(0);
  });
});
