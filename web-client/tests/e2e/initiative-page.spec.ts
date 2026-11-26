import { expect, test } from '@playwright/test';

/** Story 11.1 smoke: `/initiatives/{id}` shows the track, the strip and the current step. */
test('the Initiative page shows the workflow track and the steps strip', async ({ page }) => {
  await page.goto('/initiatives/0193a000-0000-7000-8000-0000000000f1');
  await expect(page.getByTestId('ini-workflows')).toBeVisible();
  await expect(page.getByTestId('ini-steps')).toBeVisible();
  await expect(page.getByTestId('ini-step-ux')).toHaveAttribute('aria-current', 'step');
});
