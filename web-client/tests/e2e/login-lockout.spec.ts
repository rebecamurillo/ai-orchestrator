import { type Browser, expect, test } from '@playwright/test';

import { ORCHESTRATOR_TOKEN, PREVIEW_URL } from './config';
import { NO_SESSION } from './session';

/**
 * Lockout e2e scenarios (AC 1, 2, 4). AC 3 (window expiry with fake clock) is covered
 * exclusively by `tests/unit/lockout.test.ts` because the server's `Date.now()` cannot be
 * controlled from the browser side in an Astro preview server.
 *
 * The in-memory counter is keyed by IP. In the test server all connections arrive from
 * 127.0.0.1, so the counter is shared across every context. The `beforeEach` hook submits
 * the correct token via a separate browser context, which calls `clear(ip)` in the action
 * and gives each scenario a known-zero counter state.
 *
 * `test.describe.serial` prevents within-file parallelism; without it two scenarios running
 * concurrently would contaminate each other's counter.
 *
 * The locking test (AC 2) is intentionally last: once the IP is locked, `clearIpCounter`
 * cannot un-lock it (the action rejects the correct token before reaching `clear(ip)` when
 * locked). login.spec.ts is placed in a separate Playwright project that completes before
 * this file starts (see playwright.config.ts `projects`), so it is never affected.
 */
test.use({ storageState: NO_SESSION });

/** Submit the correct token via a fresh context to clear the IP counter. */
async function clearIpCounter(browser: Browser): Promise<void> {
  const ctx = await browser.newContext({ baseURL: PREVIEW_URL });
  const page = await ctx.newPage();
  await page.goto('/login');
  await page.getByTestId('login-token').fill(ORCHESTRATOR_TOKEN);
  await Promise.all([
    page.waitForResponse((r) => r.request().method() === 'POST'),
    page.getByTestId('login-submit').click(),
  ]);
  await ctx.close();
}

test.describe.serial('login lockout', () => {
  test.beforeEach(async ({ browser }) => {
    await clearIpCounter(browser);
  });

  test('four wrong tokens show token rejected with sibling attempts count', async ({ page }) => {
    await page.goto('/login');

    for (let i = 0; i < 4; i++) {
      await page.getByTestId('login-token').fill('not-the-right-token');
      await Promise.all([
        page.waitForResponse((r) => r.request().method() === 'POST'),
        page.getByTestId('login-submit').click(),
      ]);
    }

    // The inner span carries only the label; the sibling span carries the count.
    // This preserves the pre-existing `toHaveText('token rejected')` assertions in
    // login.spec.ts (lines 95 and 116) which target this testid.
    await expect(page.getByTestId('login-rejected')).toHaveText('token rejected');
    await expect(page.getByTestId('login-attempts')).toHaveText(' — 1 attempts left');
    await expect(page.getByTestId('login-locked')).toHaveCount(0);
    await expect(page.getByTestId('login-token')).not.toBeDisabled();
    await expect(page.getByTestId('login-submit')).not.toBeDisabled();
  });

  test('correct token after two failures succeeds and resets the counter', async ({
    page,
    browser,
  }) => {
    await page.goto('/login');

    // Two wrong tokens
    for (let i = 0; i < 2; i++) {
      await page.getByTestId('login-token').fill('not-the-right-token');
      await Promise.all([
        page.waitForResponse((r) => r.request().method() === 'POST'),
        page.getByTestId('login-submit').click(),
      ]);
    }

    // Correct token clears the counter and redirects
    await page.getByTestId('login-token').fill(ORCHESTRATOR_TOKEN);
    await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'POST'),
      page.getByTestId('login-submit').click(),
    ]);
    await page.waitForURL(`${PREVIEW_URL}/`);

    // A fresh no-session context from the same IP should now start from a cleared counter.
    const ctx2 = await browser.newContext({ baseURL: PREVIEW_URL, storageState: NO_SESSION });
    const page2 = await ctx2.newPage();
    await page2.goto('/login');
    await page2.getByTestId('login-token').fill('not-the-right-token');
    await Promise.all([
      page2.waitForResponse((r) => r.request().method() === 'POST'),
      page2.getByTestId('login-submit').click(),
    ]);

    // counter cleared by the successful login, so 1 failure = 4 remaining
    await expect(page2.getByTestId('login-rejected')).toHaveText('token rejected');
    await expect(page2.getByTestId('login-attempts')).toHaveText(' — 4 attempts left');

    await ctx2.close();
  });

  // AC 2 is last: locking the IP makes clearIpCounter inoperative for any subsequent test.
  // Nothing runs after this test in this file, and login.spec.ts runs in a separate project
  // that completes before this file starts (see playwright.config.ts).
  test('fifth wrong token locks the IP and disables input and submit', async ({ page }) => {
    await page.goto('/login');

    for (let i = 0; i < 5; i++) {
      await page.getByTestId('login-token').fill('not-the-right-token');
      await Promise.all([
        page.waitForResponse((r) => r.request().method() === 'POST'),
        page.getByTestId('login-submit').click(),
      ]);
    }

    await expect(page.getByTestId('login-locked')).toHaveText(
      'too many attempts — try again in 15 min',
    );
    await expect(page.getByTestId('login-rejected')).toHaveCount(0);
    await expect(page.getByTestId('login-token')).toBeDisabled();
    await expect(page.getByTestId('login-submit')).toBeDisabled();
  });
});
