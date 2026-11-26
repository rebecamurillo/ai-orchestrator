import { expect, test } from '@playwright/test';

/** Story 10.1 smoke: `/initiatives` renders the board from the stub's fixture list. */
test('the Initiatives board renders its columns and a BLK card', async ({ page }) => {
  await page.goto('/initiatives');
  await expect(page.getByTestId('initiatives-board')).toBeVisible();
  await expect(page.getByTestId('initiatives-col-spec')).toBeVisible();
  await expect(page.getByTestId('initiatives-col-build')).toBeVisible();
  await expect(page.getByTestId('initiatives-col-done')).toBeVisible();
  await expect(page.getByTestId('initiatives-card-initiative-steps')).toContainText('BLK');
  await expect(page.getByTestId('nav-initiatives')).toHaveAttribute('aria-current', 'page');
});

test('the list view renders the dense table with a BLK row', async ({ page }) => {
  await page.goto('/initiatives?view=list');
  const row = page.getByTestId('initiatives-row-initiative-steps');
  await expect(page.getByTestId('initiatives-list')).toBeVisible();
  await expect(row).toContainText('BLK');
  await expect(row).toContainText('Orchestrator');
  await expect(row).toContainText('ux · your turn · 14 turns');
});
