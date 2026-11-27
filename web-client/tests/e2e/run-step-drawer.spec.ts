import { expect, test, type Page, type Route } from '@playwright/test';

import { runDetail, RUN_ID, withSteps } from '../fixtures/run-detail';
import { twoEpicGraph, twoEpicSteps } from '../fixtures/run-graph';
import { agentDrawer } from '../fixtures/step-drawer';

/**
 * UJ-2 (epic 2 story 2): open a story's step drawer from its Steps-table row, read the run
 * order and the log, close with Escape. Written against `page.route` mocks like
 * `run-diagram.spec.ts`; not run in the story that wrote it (B14).
 */
const BASE_URL = `/workflows/${RUN_ID}`;

async function mock(page: Page): Promise<void> {
  const steps = withSteps(twoEpicSteps());
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({ json: runDetail(steps) }),
  );
  await page.route(`**/api/runs/${RUN_ID}/graph`, (route: Route) =>
    route.fulfill({ json: twoEpicGraph() }),
  );
  await page.route(`**/api/runs/${RUN_ID}/steps/*/attempts/*/drawer`, (route: Route) =>
    route.fulfill({ json: agentDrawer() }),
  );
}

test('opens a step drawer from its row, shows run order and log, closes with Escape', async ({
  page,
}) => {
  await mock(page);
  await page.goto(BASE_URL);
  await page.getByRole('button', { name: 'STEPS' }).click();

  const opener = page.locator('button.wf-step-open').first();
  await opener.click();

  const drawer = page.getByTestId('wf-step-drawer');
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText(/^RUN ORDER · /)).toBeVisible();
  await expect(
    page.getByTestId('wf-step-drawer-log').getByText(/^LOG · ATTEMPT \d+$/),
  ).toBeVisible();
  await expect(page.locator('tr.wf-step-selected')).toHaveCount(1);

  await page.keyboard.press('Escape');
  await expect(drawer).toHaveCount(0);
  await expect(opener).toBeFocused();
});
