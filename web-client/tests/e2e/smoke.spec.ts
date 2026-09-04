import { expect, test } from '@playwright/test';

/**
 * Every page gets one smoke test (`web-client/AGENTS.md`). Story 1.4 replaced the placeholder
 * `/` with the Board inside the instrument-dark shell, which is what this now asserts is
 * served and rendered; `shell.spec.ts` covers the shell itself on all five routes.
 */
test('the board page is served', async ({ page }) => {
  const response = await page.goto('/');

  expect(response?.status()).toBe(200);
  await expect(page.locator('main')).toContainText('NOTHING REGISTERED');
});
