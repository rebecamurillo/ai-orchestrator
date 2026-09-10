import { expect, test } from '@playwright/test';

import { EXPORT_ID, EXPORT_TRAJECTORY_COUNT } from './projects-fixtures.mjs';

/**
 * *Export trajectories* on the Project screen (SPEC CAP-6, UX-DR12, FR-32 export). The
 * count, the filename and the row ordering are proven without a browser by
 * `test_trajectories_router.py` and `test_trajectory_export.py`; what only a browser proves
 * is the download itself — the link's `href`, the hint and the count as rendered, and that
 * a click crosses the real Astro proxy (`src/pages/api/[...path].ts`) to a real streamed
 * response with `Content-Disposition` intact. Deliberately not mocked with `page.route()`
 * (`stub-backend.mjs`'s own note on its new route says why).
 */

test('the bar action, the hint and the count render for a selected Project', async ({ page }) => {
  await page.goto(`/projects?id=${EXPORT_ID}`);

  const exportButton = page.getByTestId('projects-export');
  await expect(exportButton).toHaveAttribute(
    'href',
    `/api/projects/${EXPORT_ID}/trajectories.jsonl`,
  );

  const hint = page.getByTestId('projects-export-hint');
  await expect(hint).toContainText('one line per done story');
  await expect(hint).toContainText('newest first');
  await expect(hint).toContainText('JSON lines');
  await expect(hint).toContainText(`${EXPORT_TRAJECTORY_COUNT} trajectories`);
});

test('no Project selected renders no export action', async ({ page }) => {
  await page.goto('/projects');

  await expect(page.getByTestId('projects-export')).toHaveCount(0);
});

test('clicking the bar action downloads the file with its filename and content', async ({
  page,
}) => {
  await page.goto(`/projects?id=${EXPORT_ID}`);

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByTestId('projects-export').click(),
  ]);

  expect(download.suggestedFilename()).toMatch(
    /^trajectories-trajectory-source-\d{4}-\d{2}-\d{2}\.jsonl$/,
  );
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk as Buffer);
  const body = Buffer.concat(chunks).toString('utf-8');
  const lines = body.trim().split('\n');

  expect(lines).toHaveLength(EXPORT_TRAJECTORY_COUNT);
  for (const line of lines) {
    const row = JSON.parse(line) as { project_id: string; frame: string };
    expect(row.project_id).toBe(EXPORT_ID);
    expect(row.frame).toMatch(/^stories\[\d+\]$/);
  }
});
