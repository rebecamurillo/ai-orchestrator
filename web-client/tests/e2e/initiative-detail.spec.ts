import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * The Initiative detail screen (S7, `GET /initiatives/{slug}`).
 *
 * `/workflows/initiative/[slug].astro` reads nothing server-side — `InitiativeDetail`
 * does its own polled `client:load` fetch (the module doc) — so every scenario here mocks
 * `GET /api/initiatives/{slug}` with `page.route()`, `new-workflow.spec.ts`'s own precedent
 * for a route this stub does not serve: there is no initiative store behind the shared stub
 * to answer a real cross-repository DAG from.
 */

const SLUG = 'demo-initiative';
const RUN_A_EPIC = '00000000-0000-4000-8000-0000000000e1';
const RUN_A_MERGE = '00000000-0000-4000-8000-0000000000e2';
const RUN_GOLIVE = '00000000-0000-4000-8000-0000000000e3';

function view(overrides: Record<string, unknown> = {}) {
  return {
    slug: SLUG,
    repos: [
      {
        repository_id: 'repo-1',
        repository: 'orchestrator-api',
        url: 'https://github.com/example/orchestrator-api.git',
        default_branch: 'main',
        branch: 'integration/demo-initiative',
      },
    ],
    members: [
      {
        run_id: RUN_A_EPIC,
        epic_id: 'epic-a',
        role: 'epic',
        repository_id: 'repo-1',
        status: 'needs_you',
        park_kind: 'checkpoint',
        park_reason: 'spec ready for review',
        after_run_ids: [],
        template: 'epic',
        branch: 'epics/epic-a',
      },
      {
        run_id: RUN_A_MERGE,
        epic_id: 'epic-a',
        role: 'merge',
        repository_id: 'repo-1',
        status: 'queued',
        park_kind: null,
        park_reason: null,
        after_run_ids: [RUN_A_EPIC],
        template: 'merge',
        branch: 'integration/demo-initiative',
      },
      {
        run_id: RUN_GOLIVE,
        epic_id: null,
        role: 'golive',
        repository_id: 'repo-1',
        status: 'queued',
        park_kind: null,
        park_reason: null,
        after_run_ids: [RUN_A_MERGE],
        template: 'golive',
        branch: 'main',
      },
    ],
    ...overrides,
  };
}

async function mockDetail(page: Page, body: unknown, status = 200): Promise<void> {
  await page.route(`**/api/initiatives/${SLUG}`, (route: Route) =>
    route.fulfill({
      status,
      contentType: status === 200 ? 'application/json' : 'application/problem+json',
      body: JSON.stringify(body),
    }),
  );
}

test.describe('/workflows/initiative/[slug]', () => {
  test('renders repositories, epic/merge pairs and the go-live Run last', async ({ page }) => {
    await mockDetail(page, view());

    await page.goto(`/workflows/initiative/${SLUG}`);

    await expect(page.getByTestId('newin-detail')).toContainText(SLUG);
    await expect(page.getByTestId('newin-detail-repo-repo-1')).toContainText('orchestrator-api');
    await expect(page.getByTestId('newin-detail-repo-repo-1')).toContainText(
      'integration/demo-initiative',
    );
    await expect(page.getByTestId(`newin-member-${RUN_A_EPIC}`)).toContainText('CHK');
    await expect(page.getByTestId(`newin-member-${RUN_A_EPIC}-park`)).toContainText(
      'spec ready for review',
    );
    await expect(page.getByTestId(`newin-member-${RUN_A_MERGE}`)).toContainText(
      'waits for: epic-a',
    );
    await expect(page.getByTestId('newin-detail-golive')).toContainText('go-live');
    await expect(page.getByTestId(`newin-member-${RUN_GOLIVE}`)).toBeVisible();
  });

  test('links a member row to its own Run detail screen', async ({ page }) => {
    await mockDetail(page, view());

    await page.goto(`/workflows/initiative/${SLUG}`);

    await expect(
      page.getByTestId(`newin-member-${RUN_A_EPIC}`).locator('a.newin-member-link'),
    ).toHaveAttribute('href', `/workflows/${RUN_A_EPIC}`);
  });

  test('a 404 renders NO INITIATIVE UNDER {slug}, never a failed-fetch readout', async ({
    page,
  }) => {
    await mockDetail(
      page,
      { status: 404, title: 'Not Found', detail: `no initiative '${SLUG}'`, type: 'about:blank' },
      404,
    );

    await page.goto(`/workflows/initiative/${SLUG}`);

    await expect(page.getByTestId('newin-not-found')).toContainText(`NO INITIATIVE UNDER ${SLUG}`);
    await expect(page.getByTestId('fetch-failed')).toHaveCount(0);
  });

  // ── initiative-wide cancel (S8, AD-13) ─────────────────────────────────────

  test('Cancel initiative is disabled once every member has settled', async ({ page }) => {
    await mockDetail(
      page,
      view({
        members: view().members.map((member: Record<string, unknown>) => ({
          ...member,
          status: 'done',
          park_kind: null,
        })),
      }),
    );

    await page.goto(`/workflows/initiative/${SLUG}`);

    await expect(page.getByTestId('newin-cancel-trigger')).toBeDisabled();
  });

  test('Cancel initiative: confirming posts {kind: cancel}; dismissing posts nothing', async ({
    page,
  }) => {
    await mockDetail(page, view());
    await page.goto(`/workflows/initiative/${SLUG}`);
    await expect(page.getByTestId('newin-cancel-trigger')).toBeEnabled();

    let calls = 0;
    await page.route(`**/api/initiatives/${SLUG}/signals`, (route: Route) => {
      calls += 1;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ signalled: [RUN_A_EPIC, RUN_A_MERGE, RUN_GOLIVE], skipped: [] }),
      });
    });

    await page.getByTestId('newin-cancel-trigger').click();
    await expect(page.getByTestId('newin-cancel-confirm')).toContainText(
      `cancel initiative ${SLUG}?`,
    );
    await expect(page.getByTestId('newin-cancel-confirm')).toContainText('dependents first');

    await page.getByTestId('newin-cancel-confirm-no').click();
    await expect(page.getByTestId('newin-cancel-confirm')).toHaveCount(0);
    expect(calls).toBe(0);

    await page.getByTestId('newin-cancel-trigger').click();
    let posted: Record<string, unknown> | null = null;
    await page.route(`**/api/initiatives/${SLUG}/signals`, (route: Route) => {
      posted = route.request().postDataJSON() as Record<string, unknown>;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ signalled: [RUN_A_EPIC, RUN_A_MERGE, RUN_GOLIVE], skipped: [] }),
      });
    });
    await mockDetail(
      page,
      view({
        members: view().members.map((member: Record<string, unknown>) => ({
          ...member,
          status: 'cancelled',
          park_kind: null,
        })),
      }),
    );

    await page.getByTestId('newin-cancel-confirm-yes').click();

    await expect.poll(() => posted).not.toBeNull();
    expect(posted!.kind).toBe('cancel');
    await expect(page.getByTestId('newin-cancel-confirm')).toHaveCount(0);
  });
});
