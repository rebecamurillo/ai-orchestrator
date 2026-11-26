import { expect, test } from '@playwright/test';

import { CLEAN_ID } from './projects-fixtures.mjs';

/** Story 10.3 smoke: `/initiatives/new` shows the sequence, the live line, and creates. */
test('the New initiative page shows the sequence and creates an initiative', async ({ page }) => {
  await page.goto(`/initiatives/new?project=${CLEAN_ID}`);
  await expect(page.getByTestId('newini-sequence')).toBeVisible();
  await page.getByTestId('newini-name').fill('Familio Dessin v2');
  await expect(
    page.getByText('slug familio-dessin-v2 · folder initiatives/familio-dessin-v2'),
  ).toBeVisible();
  await page.getByTestId('newini-message').fill('Start with the brief.');
  await page.getByTestId('newini-create').click();
  await expect(page).toHaveURL(/\/initiatives\/0193a000-0000-7000-8000-0000000000f1$/);
});
