import { expect, test, type Page, type Route } from '@playwright/test';

import { MIXED_ID, MIXED_OK_REPO_ID } from './projects-fixtures.mjs';

/**
 * The New Initiative screen (S7).
 *
 * `GET /api/v1/projects` (the bare list) answers unconditionally empty in the shared stub
 * (`new-workflow.spec.ts`'s own precedent for the frozen `shell.spec.ts` "NO TEMPLATE TO
 * BIND" reading), so this spec opens with `?project=` — resolved through
 * `GET /projects/{id}`, exactly as a real "start a new initiative" link would. `MIXED_ID`'s
 * own `MIXED_OK_REPO_ID` repository (`projects-fixtures.mjs`, slug `orchestrator-api`) is the
 * hub repository every scenario here selects.
 *
 * **`InitiativeIn.project_id`/`repository_id` are not nullable** (`src/lib/initiative/
 * form.ts::isComplete`'s own doc), so pre-flight never fires off the bare `?project=` prefill
 * alone — every scenario fills the hub repository, base branch and initiative folder first,
 * then waits on the mocked pre-flight response itself (an `expect(...)` with the debounce's
 * own timeout) rather than on a one-shot hydration proof, since nothing here is guaranteed
 * to differ between the server-rendered markup and the hydrated one until that response
 * lands (`NewWorkflow.tsx`'s own `newwf-note` proof does not apply: this screen's initial
 * pre-flight is the *local*, no-network "form incomplete" branch, not a real round trip).
 *
 * `POST /initiatives/preflight` and `POST /initiatives` are mocked with `page.route()`, the
 * same way `new-workflow.spec.ts` mocks `/runs/preflight` and `/runs`: there is no engine
 * behind this stub to walk a real cross-repository DAG, and this screen's own ACs are about
 * rendering a given response, not about producing one.
 */

const LINK = `/workflows/new-initiative?project=${MIXED_ID}`;

const DEBOUNCED = 15_000;

function preflightBody(overrides: Record<string, unknown> = {}) {
  return {
    slug: 'demo-initiative',
    start_allowed: true,
    lines: [{ check: 'origin reachable', status: 'ok', text: 'origin ok', fix: null }],
    repos: [
      {
        repository_id: MIXED_OK_REPO_ID,
        repository: 'orchestrator-api',
        branch: 'integration/demo-initiative',
        default_branch: 'main',
        remote_holds_branch: false,
      },
    ],
    epics: [
      {
        epic_id: 'epic-a',
        title: 'Epic A',
        repository_id: MIXED_OK_REPO_ID,
        repository: 'orchestrator-api',
        branch: 'epics/epic-a',
        working_branch: 'epics/epic-a',
        depends_on: [],
        checkpoint: null,
        lines: [{ check: 'template resolves', status: 'ok', text: 'epic@1', fix: null }],
      },
    ],
    order: ['epic-a'],
    ...overrides,
  };
}

async function mockPreflight(page: Page, body: Record<string, unknown>): Promise<void> {
  await page.route('**/api/initiatives/preflight', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

/** Fills the three fields the deep link does not seed — `isComplete`'s own four — which is
 * what turns the local "form incomplete" pre-flight branch into a real `POST
 * /initiatives/preflight` call. */
async function fillRequired(page: Page): Promise<void> {
  await page.goto(LINK);
  await page.getByTestId('newin-repository').selectOption(MIXED_OK_REPO_ID);
  await page.getByTestId('newin-folder').fill('docs/initiative');
  await page.getByTestId('newin-base').fill('main');
}

test.describe('/workflows/new-initiative', () => {
  test('renders the form, the repo table and the epic list from a real pre-flight', async ({
    page,
  }) => {
    await mockPreflight(page, preflightBody());
    await fillRequired(page);

    await expect(page.getByTestId('newin-project')).toHaveValue(MIXED_ID);
    await expect(page.getByTestId('newin-repos')).toContainText('orchestrator-api', {
      timeout: DEBOUNCED,
    });
    await expect(page.getByTestId('newin-repos')).toContainText('created');
    await expect(page.getByTestId('newin-epic-epic-a')).toContainText('Epic A');
    await expect(page.getByTestId('newin-order')).toContainText('epic-a');
    await expect(page.getByTestId('newin-dispatch')).toBeEnabled();
  });

  test('refuses to dispatch while the last pre-flight said no', async ({ page }) => {
    await mockPreflight(
      page,
      preflightBody({
        start_allowed: false,
        lines: [{ check: 'base branch', status: 'fail', text: 'unknown branch', fix: null }],
      }),
    );
    await fillRequired(page);

    await expect(page.getByTestId('newin-repos')).toContainText('orchestrator-api', {
      timeout: DEBOUNCED,
    });
    await expect(page.getByTestId('newin-dispatch')).toBeDisabled();
  });

  test('a 409 on dispatch renders the problem detail', async ({ page }) => {
    await mockPreflight(page, preflightBody());
    await page.route('**/api/initiatives', (route: Route) =>
      route.fulfill({
        status: 409,
        contentType: 'application/problem+json',
        body: JSON.stringify({
          status: 409,
          title: 'Conflict',
          detail: 'a pre-flight line refuses this initiative',
          type: 'about:blank',
        }),
      }),
    );
    await fillRequired(page);
    await expect(page.getByTestId('newin-dispatch')).toBeEnabled({ timeout: DEBOUNCED });

    await page.getByTestId('newin-dispatch').click();

    await expect(page.getByTestId('newin-start-error')).toContainText(
      'a pre-flight line refuses this initiative',
    );
  });

  test('a successful dispatch navigates to the initiative detail screen', async ({ page }) => {
    await mockPreflight(page, preflightBody());
    await page.route('**/api/initiatives', (route: Route) =>
      route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          slug: 'demo-initiative',
          members: [
            {
              run_id: '00000000-0000-4000-8000-0000000000f1',
              epic_id: 'epic-a',
              role: 'epic',
              repository_id: MIXED_OK_REPO_ID,
              after_run_ids: [],
            },
          ],
          started: ['epic-a'],
        }),
      }),
    );
    // the detail screen this navigation lands on reads a real `GET /initiatives/{slug}`,
    // which this stub does not serve — mocked here too, just enough to prove the redirect
    await page.route('**/api/initiatives/demo-initiative', (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ slug: 'demo-initiative', repos: [], members: [] }),
      }),
    );
    await fillRequired(page);
    await expect(page.getByTestId('newin-dispatch')).toBeEnabled({ timeout: DEBOUNCED });

    await page.getByTestId('newin-dispatch').click();

    await expect(page).toHaveURL(/\/workflows\/initiative\/demo-initiative$/);
  });
});
