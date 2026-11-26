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
