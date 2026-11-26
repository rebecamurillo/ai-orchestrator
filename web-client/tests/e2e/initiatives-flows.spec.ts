import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * Epic 10 (orchestrator-initiative-steps) flows on `/initiatives` beyond the stub's smoke:
 * the filter segments, the cancelled-hidden toggle, the rail's need-you line and the empty
 * state. `GET /api/initiatives` is mocked with `page.route()` (`board.spec.ts` precedent),
 * since the ACs are about rendering a given response.
 */

const HOUR = 3_600_000;

function item(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    attention: null,
    id: '0193a000-0000-7000-8000-0000000000a1',
    line: 'brief · your turn',
    name: 'Initiative',
    position: 1,
    progress: '1 of 2 steps',
    project_id: '0193a000-0000-7000-8000-000000000002',
    project_name: 'Orchestrator',
    reason: '',
    repo_tag: ['ai-orchestrator'],
    repository_id: '0193a000-0000-7000-8000-000000000003',
    slug: 'initiative',
    status: 'running',
    step: 'brief',
    updated_at: new Date().toISOString(),
    workflow: 'spec',
    workflow_count: 2,
    workflows: [
      { workflow: 'spec', type: 'interactive', state: 'ongoing' },
      { workflow: 'build', type: 'auto', state: null },
    ],
    ...overrides,
  };
}

function listResponse(items: Record<string, unknown>[], counts: Record<string, unknown> = {}) {
  return {
    columns: [
      { workflow: 'spec', type: 'interactive' },
      { workflow: 'build', type: 'auto' },
      { workflow: 'deploy', type: 'auto' },
    ],
    counts: { ongoing: items.length, need_you: 0, cancelled: 0, oldest_wait_at: null, ...counts },
    items,
    next_cursor: null,
  };
}

const MIXED = listResponse(
  [
    item({ id: '0193a000-0000-7000-8000-0000000000a1', slug: 'site-redesign', name: 'Site' }),
    item({
      id: '0193a000-0000-7000-8000-0000000000a2',
      slug: 'chores-v3',
      name: 'Chores',
      status: 'waiting for her',
      updated_at: new Date(Date.now() - 49 * HOUR).toISOString(),
    }),
    item({
      id: '0193a000-0000-7000-8000-0000000000a3',
      slug: 'shipped',
      status: 'done',
      workflow: 'build',
    }),
    item({ id: '0193a000-0000-7000-8000-0000000000a4', slug: 'gone-1', status: 'cancelled' }),
    item({ id: '0193a000-0000-7000-8000-0000000000a5', slug: 'gone-2', status: 'cancelled' }),
  ],
  { ongoing: 2, need_you: 1, cancelled: 2, oldest_wait_at: new Date(Date.now() - 49 * HOUR) },
);

async function mockInitiatives(page: Page, body: unknown, seen: string[] = []): Promise<void> {
  await page.route('**/api/initiatives?*', (route: Route) => {
    seen.push(route.request().url());
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });
}

test('cards sit in their workflow column, an empty column reads —, the BLK card links to its initiative', async ({
  page,
}) => {
  await mockInitiatives(page, MIXED);
  await page.goto('/initiatives');

  const spec = page.getByTestId('initiatives-col-spec');
  await expect(spec.getByTestId('initiatives-card-site-redesign')).toBeVisible();
  await expect(spec.getByTestId('initiatives-card-chores-v3')).toContainText('BLK');
  await expect(page.getByTestId('initiatives-col-deploy')).toContainText('—');
  await expect(
    page.getByTestId('initiatives-col-done').getByTestId('initiatives-card-shipped'),
  ).toBeVisible();
  await expect(page.getByTestId('initiatives-card-chores-v3')).toHaveAttribute(
    'href',
    '/initiatives/0193a000-0000-7000-8000-0000000000a2',
  );
});

test('cancelled initiatives stay hidden until show', async ({ page }) => {
  await mockInitiatives(page, MIXED);
  await page.goto('/initiatives');

  const done = page.getByTestId('initiatives-col-done');
  await expect(done).toContainText('2 cancelled, hidden · show');
  await expect(page.getByTestId('initiatives-card-gone-1')).toHaveCount(0);

  await done.getByRole('button', { name: /cancelled, hidden/ }).click();
  await expect(page.getByTestId('initiatives-card-gone-1')).toBeVisible();
  await expect(page.getByTestId('initiatives-card-gone-2')).toBeVisible();
});

test('the rail shows the need-you line from the response counts', async ({ page }) => {
  await mockInitiatives(page, MIXED);
  await page.goto('/initiatives');

  await expect(page.getByTestId('nav-initiatives-needs-you')).toHaveText('1 need you');
  await expect(page.getByTestId('initiatives-readout')).toContainText('2 ongoing · 1 need you');
});

test('NEEDS YOU requests filter=needs_you and writes it to the URL', async ({ page }) => {
  const seen: string[] = [];
  await mockInitiatives(page, MIXED, seen);
  await page.goto('/initiatives');
  await expect(page.getByTestId('initiatives-board')).toBeVisible();

  const request = page.waitForRequest((r) => r.url().includes('filter=needs_you'));
  await page.getByTestId('initiatives-filter').getByRole('button', { name: 'NEEDS YOU' }).click();
  await request;
  await expect(page).toHaveURL(/[?&]filter=needs_you/);
  expect(seen[0]).toContain('filter=ongoing');
});

test('an empty response reads NO INITIATIVES with a link to the New initiative page', async ({
  page,
}) => {
  await mockInitiatives(page, listResponse([]));
  await page.goto('/initiatives');

  const empty = page.getByTestId('initiatives-empty');
  await expect(empty).toContainText('NO INITIATIVES');
  await expect(empty.getByRole('link', { name: 'New initiative' })).toHaveAttribute(
    'href',
    '/initiatives/new',
  );
  await expect(page.getByTestId('nav-initiatives-needs-you')).toHaveCount(0);
});

test('a failed read swaps the board for the failed-fetch readout', async ({ page }) => {
  await page.route('**/api/initiatives?*', (route: Route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/problem+json',
      body: JSON.stringify({ type: 'about:blank', title: 'Service Unavailable', status: 503 }),
    }),
  );
  await page.goto('/initiatives');

  await expect(page.getByTestId('initiatives-board')).toHaveCount(0);
  const failed = page.getByTestId('fetch-failed');
  await expect(failed).toContainText('COULD NOT REACH BACKEND-API');
  await expect(failed).toContainText('/api/initiatives?filter=ongoing');
  await expect(page.getByTestId('fetch-retry')).toBeVisible();
});
