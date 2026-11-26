import { expect, test, type Route } from '@playwright/test';

import { CLEAN_ID } from './projects-fixtures.mjs';

/**
 * Epic 10 story 3 (orchestrator-initiative-steps) refusals on `/initiatives/new`: the
 * empty-field guard, the 409 with and without an open holder, and the missing package.
 * `POST /api/initiatives` and the reads it triggers are mocked with `page.route()`.
 */

const URL = `/initiatives/new?project=${CLEAN_ID}`;
const HOLDER_ID = '0193a000-0000-7000-8000-0000000000b1';

function conflict(detail: string) {
  return (route: Route) =>
    route.fulfill({
      status: 409,
      contentType: 'application/problem+json',
      body: JSON.stringify({ type: 'about:blank', title: 'Conflict', status: 409, detail }),
    });
}

test('create stays disabled until both the name and the first message are filled', async ({
  page,
}) => {
  await page.goto(URL);
  await expect(page.getByTestId('newini-sequence')).toBeVisible();
  const create = page.getByTestId('newini-create');

  await expect(create).toBeDisabled();
  await page.getByTestId('newini-name').fill('Familio Dessin v2');
  await expect(create).toBeDisabled();
  await page.getByTestId('newini-message').fill('Start with the brief.');
  await expect(create).toBeEnabled();
  await expect(create).toHaveText('Create and start spec');
});

test('a 409 with an open holder names it, disables create, and a name edit re-enables it', async ({
  page,
}) => {
  await page.route('**/api/initiatives', conflict('slug familio-dessin-v2 is held'));
  await page.route('**/api/initiatives?*', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        columns: [],
        counts: { ongoing: 1, need_you: 0, cancelled: 0, oldest_wait_at: null },
        items: [{ id: HOLDER_ID, slug: 'familio-dessin-v2', status: 'running', step: 'ux' }],
        next_cursor: null,
      }),
    }),
  );
  await page.goto(URL);
  await expect(page.getByTestId('newini-sequence')).toBeVisible();
  await page.getByTestId('newini-name').fill('Familio Dessin v2');
  await page.getByTestId('newini-message').fill('Start with the brief.');
  await page.getByTestId('newini-create').click();

  const taken = page.getByTestId('newini-slug-taken');
  await expect(taken).toHaveText(
    "slug familio-dessin-v2 is used by an open initiative: familio-dessin-v2 (ux, running). A cancelled initiative's slug is free.",
  );
  await expect(taken.getByRole('link', { name: 'familio-dessin-v2' })).toHaveAttribute(
    'href',
    `/initiatives/${HOLDER_ID}`,
  );
  await expect(page.getByTestId('newini-create')).toBeDisabled();

  await page.getByTestId('newini-name').fill('Familio Dessin v3');
  await expect(page.getByTestId('newini-slug-taken')).toHaveCount(0);
  await expect(page.getByTestId('newini-create')).toBeEnabled();
});

test('a 409 with no open holder renders the problem detail and disables create', async ({
  page,
}) => {
  const detail = 'slug familio-dessin-v2 waits for its branch cleanup: spec/familio-dessin-v2';
  await page.route('**/api/initiatives', conflict(detail));
  await page.route('**/api/initiatives?*', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        columns: [],
        counts: { ongoing: 0, need_you: 0, cancelled: 0, oldest_wait_at: null },
        items: [],
        next_cursor: null,
      }),
    }),
  );
  await page.goto(URL);
  await expect(page.getByTestId('newini-sequence')).toBeVisible();
  await page.getByTestId('newini-name').fill('Familio Dessin v2');
  await page.getByTestId('newini-message').fill('Start with the brief.');
  await page.getByTestId('newini-create').click();

  await expect(page.getByText(detail)).toBeVisible();
  await expect(page.getByTestId('newini-slug-taken')).toHaveCount(0);
  await expect(page.getByTestId('newini-create')).toBeDisabled();
});

test('a project with no package reads the no-package line and cannot create', async ({ page }) => {
  await page.route('**/api/projects/*/package', (route: Route) =>
    route.fulfill({
      status: 404,
      contentType: 'application/problem+json',
      body: JSON.stringify({ type: 'about:blank', title: 'Not Found', status: 404 }),
    }),
  );
  await page.goto(URL);

  await expect(
    page.getByText("no package installed · install one in the project's Package section"),
  ).toBeVisible();
  await expect(page.getByTestId('newini-sequence')).toHaveCount(0);
  await page.getByTestId('newini-name').fill('Familio Dessin v2');
  await page.getByTestId('newini-message').fill('Start with the brief.');
  await expect(page.getByTestId('newini-create')).toBeDisabled();
});
