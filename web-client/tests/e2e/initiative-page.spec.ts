import { expect, test } from '@playwright/test';

/** Story 11.1 smoke: `/initiatives/{id}` shows the track, the strip and the current step. */
test('the Initiative page shows the workflow track and the steps strip', async ({ page }) => {
  await page.goto('/initiatives/0193a000-0000-7000-8000-0000000000f1');
  await expect(page.getByTestId('ini-workflows')).toBeVisible();
  await expect(page.getByTestId('ini-steps')).toBeVisible();
  await expect(page.getByTestId('ini-step-ux')).toHaveAttribute('aria-current', 'step');
});

/** Story 11.2: a message sent with Ctrl+Enter shows as queued behind the running turn. */
test('a sent message shows queued behind the running turn', async ({ page }) => {
  await page.goto('/initiatives/0193a000-0000-7000-8000-0000000000f1');
  const box = page.getByTestId('ini-message');
  await box.fill('Also the parent can hide a drawing.');
  await box.press('Control+Enter');
  await expect(
    page.getByText('queued · waits for turn 15 to finish: "Also the parent can hide a drawing."'),
  ).toBeVisible();
});

/** Story 11.3: a file of the right column opens read-only in the artifact modal. */
test('a file opens read-only from the right column', async ({ page }) => {
  await page.goto('/initiatives/0193a000-0000-7000-8000-0000000000f1');
  await page.getByTestId('ini-files').getByTestId('ini-file').click();
  await expect(page.getByTestId('wf-artifact-modal')).toBeVisible();
  await expect(page.getByTestId('wf-artifacts-edit')).toHaveCount(0);
});

/** Story 11.4: the forced-start confirmation opens on Start now and Escape dismisses it. */
test('Start now opens its confirmation and Escape closes it', async ({ page }) => {
  await page.goto('/initiatives/0193a000-0000-7000-8000-0000000000f1');
  await page.getByTestId('ini-force-plan').click();
  await expect(page.getByRole('dialog')).toContainText('START PLAN NOW');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

/** Story 11.4: the cancel confirmation lists what is removed and closes once confirmed. */
test('Cancel initiative lists four lines and confirms', async ({ page }) => {
  await page.goto('/initiatives/0193a000-0000-7000-8000-0000000000f1');
  await page.getByTestId('ini-cancel').click();
  const plane = page.getByRole('dialog');
  await expect(plane).toContainText('CANCEL INITIATIVE');
  await expect(plane.locator('li')).toHaveCount(4);
  await page.getByTestId('ini-cancel-confirm').click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
