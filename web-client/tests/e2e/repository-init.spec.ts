import { expect, test } from '@playwright/test';

import { MIXED_ID } from './projects-fixtures.mjs';

/**
 * *Initialise repository* (4.10, UX-DR12) on the Projects detail pane.
 *
 * The endpoint's own rules (409s, the completion hook) are `tests/e2e/
 * test_repository_init.py`'s subject against the real engine; `stub-backend.mjs`'s
 * `initRepository` cannot walk a real plan, so it simulates the whole Run reaching `done` in
 * one response. What this file proves is what only a real page can show: the control renders
 * for a `missing` method and not for an `ok` one, and a real click does a full round trip
 * with no client JavaScript and updates the row.
 */

test('the control renders only on a row whose method needs it', async ({ page }) => {
  await page.goto(`/projects?id=${MIXED_ID}`);

  await expect(page.getByTestId('projects-init-orchestrator-init')).toBeVisible();
  await expect(page.getByTestId('projects-init-orchestrator-init')).toHaveText(
    'Initialise repository',
  );
  await expect(page.getByTestId('projects-init-orchestrator-api')).toHaveCount(0);
});

test('clicking it does a full round trip with no client JavaScript and updates the row', async ({
  page,
}) => {
  await page.goto(`/projects?id=${MIXED_ID}`);
  const row = page.getByTestId('projects-repo-orchestrator-init');
  await expect(row.getByTestId('projects-init-orchestrator-init')).toBeVisible();

  const [response] = await Promise.all([
    page.waitForResponse((candidate) => candidate.request().method() === 'POST'),
    row.getByTestId('projects-init-orchestrator-init').click(),
  ]);

  expect(response.status()).toBe(200);
  expect(new URL(page.url()).searchParams.get('id')).toBe(MIXED_ID);
  await expect(row.getByTestId('projects-init-orchestrator-init')).toHaveCount(0);
  // the stub does not merge `chore/bmad-init` into `main` any more than the real backend
  // does (AD-16): the method cell stays `missing` and the control reads `initialised ·
  // link` rather than a version it cannot honestly claim yet (`RepositoriesTable.astro`)
  const status = row.getByTestId('projects-init-orchestrator-init-status');
  await expect(status).toContainText('initialised ·');
  await expect(status).not.toContainText('initialised · v');
  await expect(status.getByRole('link', { name: 'link' })).toHaveAttribute(
    'href',
    /compare\/main\.\.\.chore\/bmad-init/,
  );

  const runs = page.getByTestId('projects-runs');
  await expect(runs).toBeVisible();
  await expect(runs).toContainText('repo-init@1');
});

test('a repository whose method is ok never renders the control', async ({ page }) => {
  await page.goto(`/projects?id=${MIXED_ID}`);

  const row = page.getByTestId('projects-repo-orchestrator-api');
  await expect(row).toContainText('6.11.0');
  await expect(row.getByTestId(`projects-init-orchestrator-api`)).toHaveCount(0);
});
