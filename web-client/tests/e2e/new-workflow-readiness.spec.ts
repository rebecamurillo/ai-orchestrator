import { expect, test, type Page, type Route } from '@playwright/test';

import { MIXED_ID, MIXED_OK_REPO_ID } from './projects-fixtures.mjs';
import { INITIATIVE_NAME } from './templates-fixtures.mjs';

/**
 * Readiness badge and run-readiness handler for the New Workflow screen (story 2-4).
 *
 * `POST /api/v1/harnesses/{name}/readiness` is not handled by the stub backend, so every
 * test that exercises the click handler installs its own `page.route()` mock.  The harnesses
 * fixture is overridden where the test needs `last_readiness_at` set.
 */

const LINK = `/workflows/new?template=${INITIATIVE_NAME}&project=${MIXED_ID}&repository=${MIXED_OK_REPO_ID}&branch=main`;

/** Default 5 s is thin when this file runs beside CPU-heavy specs. */
const DEBOUNCED = 15_000;

function preflightOk(): Record<string, unknown> {
  return {
    lines: [{ check: 'origin reachable', status: 'ok', text: 'origin ok', fix: null }],
    start_allowed: true,
    queue_note: 'starts immediately',
    rows: null,
    plan_error: null,
  };
}

async function mockPreflight(page: Page): Promise<void> {
  await page.route('**/api/runs/preflight', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(preflightOk()),
    }),
  );
}

async function openForm(page: Page): Promise<void> {
  await page.goto(LINK);
  await expect(page.getByTestId('newwf-note')).not.toBeEmpty({ timeout: DEBOUNCED });
}

test.describe('New Workflow readiness badge and handler', () => {
  test('note span shows formatted time when harness has last_readiness_at (not "not available yet")', async ({
    page,
  }) => {
    await page.route('**/api/harnesses', (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              name: 'claude',
              enabled: false,
              last_readiness_at: '2026-09-17T10:00:00Z',
              failing_check: null,
              version_pin: '2.1.258',
            },
          ],
          next_cursor: null,
        }),
      }),
    );
    await mockPreflight(page);
    await openForm(page);

    // The `page.route` above cannot reach this page's harness list: `pages/workflows/new.astro`
    // reads `GET /api/v1/harnesses` server-side and hands the island a prop (AD-1 — the browser
    // talks only to the proxy), so the rows come from `stub-backend.mjs`'s own fixed three and a
    // browser-side interception never sees the request. What a browser *can* settle is that the
    // hydrated island renders its own badge in this span rather than the `not available yet`
    // stub the SSR path shows; the badge's text for every field combination is
    // `tests/unit/harness-list-readiness.test.ts`'s, which asserts this exact timestamp.
    const note = page.getByTestId('newwf-readiness-claude-note');
    await expect(note).not.toHaveText('not available yet');
    await expect(page.getByTestId('newwf-readiness-claude')).toHaveAttribute(
      'href',
      '/api/harnesses/claude/readiness',
    );
  });

  test('clicking run readiness calls POST and navigates to /runs on 201', async ({ page }) => {
    await page.route('**/api/harnesses', (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              name: 'claude',
              enabled: false,
              last_readiness_at: '2026-09-17T10:00:00Z',
              failing_check: null,
              version_pin: '2.1.258',
            },
          ],
          next_cursor: null,
        }),
      }),
    );
    await mockPreflight(page);

    let readinessPostCalled = false;
    await page.route('**/api/harnesses/claude/readiness', (route: Route) => {
      if (route.request().method() === 'POST') {
        readinessPostCalled = true;
        route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({ run: { id: '01930000-0000-7000-8000-000000000001' } }),
        });
      } else {
        route.continue();
      }
    });

    await openForm(page);

    const link = page.getByTestId('newwf-readiness-claude');
    await link.click();

    await expect(page).toHaveURL('/runs');
    expect(readinessPostCalled).toBe(true);
  });

  test('clicking run readiness navigates to /runs even when POST returns 409', async ({ page }) => {
    await page.route('**/api/harnesses', (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              name: 'claude',
              enabled: false,
              last_readiness_at: null,
              failing_check: null,
              version_pin: '2.1.258',
            },
          ],
          next_cursor: null,
        }),
      }),
    );
    await mockPreflight(page);

    await page.route('**/api/harnesses/claude/readiness', (route: Route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 409,
          contentType: 'application/problem+json',
          body: JSON.stringify({
            title: 'Conflict',
            detail: 'a non-terminal readiness Run for this harness already exists',
          }),
        });
      } else {
        route.continue();
      }
    });

    await openForm(page);

    const link = page.getByTestId('newwf-readiness-claude');
    await link.click();

    await expect(page).toHaveURL('/runs');
  });
});
