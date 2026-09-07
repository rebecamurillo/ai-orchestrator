import { expect, test, type Page, type Route } from '@playwright/test';

import { MIXED_FAILED_REPO_ID, MIXED_ID, MIXED_OK_REPO_ID } from './projects-fixtures.mjs';
import { INITIATIVE_NAME } from './templates-fixtures.mjs';

/**
 * The New Workflow screen (4.13, SPEC CAP-13, UX-DR8).
 *
 * `GET /api/v1/templates` and `GET /api/v1/projects` (the bare lists) answer unconditionally
 * empty in the shared stub (the frozen `shell.spec.ts`'s own "NO TEMPLATE TO BIND" reading of
 * bare `/workflows/new`), so every spec here opens with `?template=` and `?project=` — the
 * brief's own prefill contract — which `new.astro` resolves through
 * `GET /templates/{name}/versions` and `GET /projects/{id}`, exactly as a real "start a new
 * run" link would. `MIXED_ID` (2.4's own fixture) carries both an `ok` and a `failed`
 * Repository, which doubles as this story's own fixture for the clone-check note.
 *
 * `POST /runs/preflight` and `POST /runs` are mocked with `page.route()`, the same way
 * `template-diagram.spec.ts` mocks `/templates/*graph` and `/validate`: there is no engine
 * behind this stub to walk a real plan, and the ACs are about rendering a given response, not
 * about producing one.
 */

const LINK = `/workflows/new?template=${INITIATIVE_NAME}&project=${MIXED_ID}&repository=${MIXED_OK_REPO_ID}&branch=main`;

const RED = 'rgb(224, 82, 82)';

function preflightBody(overrides: Record<string, unknown> = {}) {
  return {
    lines: [{ check: 'origin reachable', status: 'ok', text: 'origin ok', fix: null }],
    start_allowed: true,
    queue_note: 'starts immediately if the repository is free',
    rows: [
      {
        seq: 1,
        path: 'plan',
        label: 'plan',
        kind: 'plan.check',
        gate: 'deterministic',
        status: 'planned',
        reason: null,
        with_resolved: {},
        frame: null,
        story_id: null,
      },
    ],
    plan_error: null,
    ...overrides,
  };
}

async function mockPreflight(page: Page, body: Record<string, unknown>): Promise<void> {
  await page.route('**/api/runs/preflight', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

test.describe('/workflows/new', () => {
  test('pre-selects initiative, shows its input, and swaps to epic on switch; repo-init hides the harness list', async ({
    page,
  }) => {
    await mockPreflight(page, preflightBody());
    await page.goto(LINK);

    await expect(page.getByTestId('newwf-template')).toHaveValue('initiative');
    await expect(page.getByTestId('newwf-input-initiative_folder')).toBeVisible();
    await expect(page.getByTestId('newwf-harness-claude')).toBeVisible();

    await page.getByTestId('newwf-template').selectOption('epic');

    await expect(page.getByTestId('newwf-input-initiative_folder')).toHaveCount(0);
    await expect(page.getByTestId('newwf-input-branch')).toBeVisible();
    await expect(page.getByTestId('newwf-input-spec_folder')).toBeVisible();

    await page.getByTestId('newwf-template').selectOption('repo-init');

    await expect(page.getByTestId('newwf-harness-claude')).toHaveCount(0);
  });

  test('a disabled harness reads its own line and is not selectable', async ({ page }) => {
    await mockPreflight(page, preflightBody());
    await page.goto(LINK);

    const claude = page.getByTestId('newwf-harness-claude');
    await expect(claude).toContainText(
      'claude · disabled: no readiness run · last readiness — · re-run readiness',
    );
    await expect(claude.locator('input[type="radio"]')).toBeDisabled();
  });

  test('a fail line shows its fix, disables Start run, and colours only the x', async ({
    page,
  }) => {
    await mockPreflight(
      page,
      preflightBody({
        start_allowed: false,
        lines: [
          {
            check: 'harness',
            status: 'fail',
            text: 'claude is disabled',
            fix: 'run readiness for claude first',
          },
        ],
      }),
    );
    await page.goto(LINK);

    const line = page.getByTestId('newwf-preflight-harness');
    await expect(line).toContainText('x');
    await expect(line).toContainText('run readiness for claude first');
    await expect(page.getByTestId('newwf-start')).toBeDisabled();

    const word = line.locator('[data-signal="failed"]');
    await expect(word).toHaveCSS('color', RED);
    await expect(line).not.toHaveCSS('color', RED);
  });

  test('the plan table lists every row, plan first, a skipped row as plain text', async ({
    page,
  }) => {
    await mockPreflight(
      page,
      preflightBody({
        rows: [
          {
            seq: 1,
            path: 'plan',
            label: 'plan',
            kind: 'plan.check',
            gate: 'deterministic',
            status: 'planned',
            reason: null,
            with_resolved: {},
            frame: null,
            story_id: null,
          },
          {
            seq: 2,
            path: 'story-1',
            label: 'story-1',
            kind: 'agent',
            gate: 'human',
            status: 'skipped',
            reason: 'already done',
            with_resolved: {},
            frame: null,
            story_id: 'story-1',
          },
        ],
      }),
    );
    await page.goto(LINK);

    await expect(page.getByTestId('newwf-plan-row-1')).toContainText('plan');
    await expect(page.getByTestId('newwf-plan-row-1')).toContainText('plan.check');
    await expect(page.getByTestId('newwf-plan-row-2')).toContainText('skipped · already done');
  });

  test('Start run navigates on 201, and keeps the form with the detail shown on 409', async ({
    page,
  }) => {
    await mockPreflight(page, preflightBody());
    await page.goto(LINK);
    await expect(page.getByTestId('newwf-start')).toBeEnabled();

    await page.getByTestId('newwf-budget').fill('50');

    await page.route('**/api/runs', (route: Route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      return route.fulfill({
        status: 409,
        contentType: 'application/problem+json',
        body: JSON.stringify({
          type: 'about:blank',
          title: 'conflict',
          status: 409,
          detail: 'a Run is already queued for this repository',
        }),
      });
    });
    await page.getByTestId('newwf-start').click();

    await expect(page.getByTestId('newwf-start-error')).toContainText(
      'a Run is already queued for this repository',
    );
    await expect(page.getByTestId('newwf-form')).toBeVisible();

    const runId = '01a06887-79ab-759b-97a0-71c32ad939ff';
    await page.route('**/api/runs', (route: Route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          run: {
            id: runId,
            status: 'queued',
            template: 'initiative',
            version: 1,
            project: MIXED_ID,
            repository: MIXED_OK_REPO_ID,
            branch: 'main',
            budget_usd: '50',
            spend_usd: '0',
            plan_ref: null,
            created_at: '2026-09-07T09:00:00Z',
            admitted_signals: [],
          },
          starts_now: true,
          waiting: '',
        }),
      });
    });
    await page.getByTestId('newwf-start').click();

    await expect(page).toHaveURL(`/workflows/${runId}`);
  });

  test('a failed clone check on the selected repository names the note', async ({ page }) => {
    await mockPreflight(page, preflightBody());
    await page.goto(
      `/workflows/new?template=${INITIATIVE_NAME}&project=${MIXED_ID}&repository=${MIXED_FAILED_REPO_ID}`,
    );

    await expect(page.getByTestId('newwf-repository')).toHaveValue(MIXED_FAILED_REPO_ID);
    await expect(page.locator('.newwf-field-note')).toContainText(
      'clone check failed · new runs blocked',
    );
  });

  test('a reload restores the form from the query string and re-runs pre-flight', async ({
    page,
  }) => {
    await mockPreflight(page, preflightBody());
    await page.goto(LINK);
    await page.getByTestId('newwf-template').selectOption('epic');
    await page.getByTestId('newwf-input-branch').fill('chore/my-epic');
    await page.waitForURL((url) => url.searchParams.get('in_branch') === 'chore/my-epic');

    let preflightCalls = 0;
    await page.route('**/api/runs/preflight', (route: Route) => {
      preflightCalls += 1;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(preflightBody()),
      });
    });

    await page.reload();

    await expect(page.getByTestId('newwf-template')).toHaveValue('epic');
    await expect(page.getByTestId('newwf-input-branch')).toHaveValue('chore/my-epic');
    await expect.poll(() => preflightCalls).toBeGreaterThan(0);
  });
});
