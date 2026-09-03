import { expect, test } from '@playwright/test';

/**
 * Every page gets one smoke test (`web-client/AGENTS.md`). `/` is a placeholder until 1.4
 * replaces it with the Board, so this asserts the route is served and rendered, nothing more.
 */
test('the placeholder page is served', async ({ page }) => {
  const response = await page.goto('/');

  expect(response?.status()).toBe(200);
  await expect(page.locator('main')).toHaveText('web-client up');
});
