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

/** *Start run* comes back only after the 400 ms debounce and the round trip behind it. The
 * default 5 s expect timeout is thin for that when this file runs beside the CodeMirror
 * specs, which saturate the CPU typing character by character. */
const DEBOUNCED = 15_000;

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

/**
 * Open the screen and wait until its `client:load` island is actually live.
 *
 * Hydration is what binds the form's handlers, and until it lands the controls are inert
 * server-rendered markup: a `selectOption` before it is written straight back by React's own
 * controlled `value` on the first render, and the template inputs it should have swapped in
 * never appear. The queue note is empty in the server render and carries text only once the
 * island's own first pre-flight has been applied, so it is the one signal that the island is
 * mounted, has fetched, and has re-rendered.
 */
async function openForm(page: Page, url: string = LINK): Promise<void> {
  await page.goto(url);
  await expect(page.getByTestId('newwf-note')).not.toBeEmpty({ timeout: DEBOUNCED });
}

test.describe('/workflows/new', () => {
  test('pre-selects initiative, shows its input, and swaps to epic on switch; repo-init hides the harness list', async ({
    page,
  }) => {
    await mockPreflight(page, preflightBody());
    await openForm(page);

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

  test('a harness with a failing probe reads its failing_reason line and is not selectable (Operator decision 2026-09-17: probe-based gating)', async ({
    page,
  }) => {
    // Operator decision 2026-09-17: harnesses are no longer gated by HarnessOut.enabled on
    // initial render; gating is probe-based.  A harness is initially selectable and becomes
    // disabled only after a probe returns ok=false.
    await mockPreflight(page, preflightBody());
    await page.route('**/api/harnesses/claude/probe', (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: false,
          failing_reason: 'not logged in',
          models: [],
          version: '',
        }),
      }),
    );
    await page.goto(LINK);

    const claude = page.getByTestId('newwf-harness-claude');
    // Radio is initially enabled — no probe result yet
    await expect(claude.locator('input[type="radio"]')).toBeEnabled();
    // Click to trigger probe
    await claude.locator('input[type="radio"]').click();
    // After probe returns failing, radio becomes disabled and row shows failing_reason
    await expect(claude.locator('input[type="radio"]')).toBeDisabled({ timeout: DEBOUNCED });
    await expect(claude).toContainText('not logged in');
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
    await openForm(page);
    await expect(page.getByTestId('newwf-start')).toBeEnabled();

    await page.getByTestId('newwf-budget').fill('50');
    // the edit invalidates the pre-flight that authorised the button; it comes back once the
    // debounced re-run answers
    await expect(page.getByTestId('newwf-start')).toBeEnabled({ timeout: DEBOUNCED });

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
    await openForm(page);
    await page.getByTestId('newwf-template').selectOption('epic');
    await page.getByTestId('newwf-input-branch').fill('chore/my-epic');
    // `history.replaceState` is not a navigation `waitForURL` can be relied on to observe
    await expect
      .poll(() => new URL(page.url()).searchParams.get('in_branch'))
      .toBe('chore/my-epic');

    let preflightCalls = 0;
    let sent: Record<string, unknown> | null = null;
    await page.route('**/api/runs/preflight', (route: Route) => {
      preflightCalls += 1;
      sent = route.request().postDataJSON() as Record<string, unknown>;
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
    // the restored state is what pre-flight was re-run *with*, not merely that a call happened
    expect(sent!.template_name).toBe('epic');
    expect(sent!.inputs).toMatchObject({ branch: 'chore/my-epic' });
  });

  test('renders the queue note verbatim and offers Cancel back to the board', async ({ page }) => {
    await mockPreflight(
      page,
      preflightBody({ queue_note: 'queues behind epic · chore/other-epic' }),
    );
    await page.goto(LINK);

    await expect(page.getByTestId('newwf-note')).toHaveText(
      'queues behind epic · chore/other-epic',
    );
    await expect(page.getByTestId('newwf-cancel')).toHaveAttribute('href', '/');
  });

  test('posts the resolved template version and the bound inputs to /runs', async ({ page }) => {
    await mockPreflight(page, preflightBody());
    await openForm(page, `${LINK}&in_initiative_folder=docs/initiative`);
    await page.getByTestId('newwf-budget').fill('25');
    await expect(page.getByTestId('newwf-start')).toBeEnabled({ timeout: DEBOUNCED });

    let posted: Record<string, unknown> | null = null;
    await page.route('**/api/runs', (route: Route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      posted = route.request().postDataJSON() as Record<string, unknown>;
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          run: { id: '01a06887-79ab-759b-97a0-71c32ad939fe' },
          starts_now: true,
          waiting: '',
        }),
      });
    });
    await page.getByTestId('newwf-start').click();

    await expect.poll(() => posted).not.toBeNull();
    expect(posted!.template_name).toBe('initiative');
    // resolved from GET /templates/{name}/versions, never left null
    expect(posted!.template_version).toBe(1);
    expect(posted!.budget_usd).toBe('25');
    expect(posted!.base_branch).toBe('main');
    expect(posted!.inputs).toEqual({ initiative_folder: 'docs/initiative' });
  });

  test('switching to a template the list read did not carry still resolves its version', async ({
    page,
  }) => {
    await mockPreflight(page, preflightBody());
    await openForm(page);
    await page.getByTestId('newwf-template').selectOption('epic');
    await page.getByTestId('newwf-input-branch').fill('chore/x');
    await page.getByTestId('newwf-input-spec_folder').fill('specs/');
    await page.getByTestId('newwf-budget').fill('25');
    await expect(page.getByTestId('newwf-start')).toBeEnabled({ timeout: DEBOUNCED });

    let posted: Record<string, unknown> | null = null;
    await page.route('**/api/runs', (route: Route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      posted = route.request().postDataJSON() as Record<string, unknown>;
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          run: { id: '01a06887-79ab-759b-97a0-71c32ad939fd' },
          starts_now: true,
          waiting: '',
        }),
      });
    });
    await page.getByTestId('newwf-start').click();

    await expect.poll(() => posted).not.toBeNull();
    expect(posted!.template_name).toBe('epic');
    expect(posted!.template_version).toBe(1);
  });

  test('Start run with a required field still empty states the reason rather than doing nothing', async ({
    page,
  }) => {
    // pre-flight says yes (its own fields are all optional) while budget is still empty
    await mockPreflight(page, preflightBody());
    await openForm(page);
    await expect(page.getByTestId('newwf-start')).toBeEnabled();
    await expect(page.getByTestId('newwf-budget')).toHaveValue('');

    await page.getByTestId('newwf-start').click();

    await expect(page.getByTestId('newwf-start-error')).toContainText(
      'every field but model and manual estimate is required',
    );
  });

  test('the re-run readiness link points at the endpoint and says it is not served yet', async ({
    page,
  }) => {
    // Operator decision 2026-09-17: harnesses are initially enabled (probe-based gating);
    // the re-run readiness link is offered regardless of probe state.
    await mockPreflight(page, preflightBody());
    await page.goto(LINK);

    await expect(page.getByTestId('newwf-readiness-claude')).toHaveAttribute(
      'href',
      '/api/harnesses/claude/readiness',
    );
    await expect(page.getByTestId('newwf-readiness-claude-note')).toHaveText('not available yet');
    // Initially enabled — no probe result yet on page load
    await expect(page.getByTestId('newwf-harness-claude').locator('input')).toBeEnabled();
  });

  test('a pre-flight that cannot be read says so instead of rendering an empty column', async ({
    page,
  }) => {
    await page.route('**/api/runs/preflight', (route: Route) => route.abort());
    await page.goto(LINK);

    await expect(page.getByTestId('newwf-preflight-failed')).toContainText(
      'pre-flight could not be read from backend-api',
    );
    await expect(page.getByTestId('newwf-start')).toBeDisabled();
  });

  test('a plan error replaces the table with one red line', async ({ page }) => {
    await mockPreflight(
      page,
      preflightBody({
        rows: null,
        plan_error: {
          reason: 'unknown input',
          template: 'initiative',
          version: 1,
          line: 4,
          item: 'initiative_folder',
        },
      }),
    );
    await page.goto(LINK);

    const plan = page.getByTestId('newwf-plan');
    await expect(plan).toHaveText('plan error · initiative@1 · line 4 · unknown input');
    await expect(plan).toHaveCSS('color', RED);
  });

  test('a deep link naming a repository but no branch opens with the default branch bound', async ({
    page,
  }) => {
    await mockPreflight(page, preflightBody());
    await page.goto(
      `/workflows/new?template=${INITIATIVE_NAME}&project=${MIXED_ID}&repository=${MIXED_OK_REPO_ID}`,
    );

    await expect(page.getByTestId('newwf-base')).toHaveValue('main');
  });

  test('a deep link naming a repository of another project drops it rather than posting it', async ({
    page,
  }) => {
    await mockPreflight(page, preflightBody());
    await page.goto(
      `/workflows/new?template=${INITIATIVE_NAME}&project=${MIXED_ID}&repository=00000000-0000-4000-8000-0000000000ff`,
    );

    await expect(page.getByTestId('newwf-repository')).toHaveValue('');
  });

  test('one debounced pre-flight covers a burst of keystrokes', async ({ page }) => {
    await mockPreflight(page, preflightBody());
    await openForm(page);
    await expect(page.getByTestId('newwf-preflight-origin-reachable')).toBeVisible();

    let calls = 0;
    await page.route('**/api/runs/preflight', (route: Route) => {
      calls += 1;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(preflightBody()),
      });
    });

    await page.getByTestId('newwf-base').fill('a-long-branch-name-typed-in-one-go');

    await expect.poll(() => calls).toBeGreaterThan(0);
    // 400 ms after the last change, not once per character
    expect(calls).toBe(1);
  });
});
