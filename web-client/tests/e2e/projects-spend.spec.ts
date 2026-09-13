import { expect, test } from '@playwright/test';

import { SPEND_FAILED_ID, SPEND_ID, SPEND_PROVISIONAL_ID } from './projects-fixtures.mjs';

/**
 * Per-project monthly spend on the Projects screen (story 8-6).
 *
 * `GET /api/v1/projects` is server-side and answers unconditionally empty in the stub
 * (frozen `shell.spec.ts` constraint), so the three spend scenarios are proven through
 * the detail pane (`?id=`) rather than through the list. The list row count rendering
 * (priority: `needsYouCount` amber vs `failedCount` red) is proven at the component layer
 * instead, in `tests/unit/project-list-row-counts.test.ts` — the same approach
 * `projects.spec.ts` (2.4) takes for "Two rows render, one selected".
 *
 * Three dedicated fixtures in `projects-fixtures.mjs` cover the three AC scenarios:
 * - `SPEND` — settled spend ($3.50, not provisional), `needs_you_count=1`
 * - `SPEND_PROVISIONAL` — provisional spend ($5.40)
 * - `SPEND_FAILED` — no spend, `failed_recent_count=2`
 */

test.describe('?id=<SPEND> — settled spend', () => {
  test('meta line shows this month spend amount', async ({ page }) => {
    await page.goto(`/projects?id=${SPEND_ID}`);

    const detail = page.getByTestId('projects-detail');
    await expect(detail).toBeVisible();
    await expect(detail.locator('.meta').first()).toContainText('this month $3.50');
  });

  test('meta line does not show the word provisional', async ({ page }) => {
    await page.goto(`/projects?id=${SPEND_ID}`);

    const detail = page.getByTestId('projects-detail');
    await expect(detail).toBeVisible();
    const metaText = await detail.locator('.meta').first().innerText();
    expect(metaText).not.toContain('provisional');
  });
});

test.describe('?id=<SPEND_PROVISIONAL> — provisional spend', () => {
  test('meta line shows the spend amount with the word provisional', async ({ page }) => {
    await page.goto(`/projects?id=${SPEND_PROVISIONAL_ID}`);

    const detail = page.getByTestId('projects-detail');
    await expect(detail).toBeVisible();
    await expect(detail.locator('.meta').first()).toContainText('this month $5.40 provisional');
  });
});

test.describe('?id=<SPEND_FAILED> — no spend, failed runs', () => {
  test('meta line shows zero spend', async ({ page }) => {
    await page.goto(`/projects?id=${SPEND_FAILED_ID}`);

    const detail = page.getByTestId('projects-detail');
    await expect(detail).toBeVisible();
    await expect(detail.locator('.meta').first()).toContainText('this month $0.00');
  });
});
