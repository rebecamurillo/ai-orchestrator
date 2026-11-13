import { expect, test } from '@playwright/test';

test('the Metrics page shows its bar, the rail item and the no-project line', async ({ page }) => {
  await page.goto('/metrics');
  await expect(page.getByTestId('surface-title')).toHaveText('METRICS');
  await expect(page.getByTestId('nav-metrics')).toHaveAttribute('aria-current', 'page');
  await expect(page.getByTestId('metrics-no-project')).toBeVisible();
  // the stub backend has no /metrics/* routes
  await expect(page.getByTestId('metrics-spend-failed')).toBeVisible();
});
