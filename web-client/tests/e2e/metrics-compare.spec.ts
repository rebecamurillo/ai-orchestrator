import { expect, test } from '@playwright/test';

test('the comparison asks for two Runs, and reads the API for two', async ({ page }) => {
  await page.goto('/metrics/compare?runs=a');
  await expect(page.getByTestId('surface-title')).toHaveText('COMPARE');
  await expect(page.getByTestId('compare-too-few')).toBeVisible();

  // the stub backend has no /metrics/* routes
  await page.goto('/metrics/compare?runs=a,b');
  await expect(page.getByTestId('compare-failed')).toBeVisible();
});
