import { expect, test, type Page, type Route } from '@playwright/test';

import { MIXED_ID, MIXED_OK_REPO_ID } from './projects-fixtures.mjs';
import { INITIATIVE_NAME, STORY_RUN_NAME } from './templates-fixtures.mjs';

/**
 * Model-named Template inputs follow the selected harness's probe exactly as MODEL does
 * (spec-model-input-selectors, 2026-10-30). The probe is stubbed with `page.route()`, as in
 * `new-workflow-probe.spec.ts`; the Template's `model_x` / `model_y` inputs are this suite's
 * own fixture data (`templates-fixtures.mjs`). "Cleared" is asserted on the `POST /runs` body,
 * never on a select's DOM value: React shows the blank option whatever the state holds.
 */

const base = (template: string) =>
  `/workflows/new?template=${template}&project=${MIXED_ID}&repository=${MIXED_OK_REPO_ID}&branch=main`;
const LINK = base(STORY_RUN_NAME);
const DEBOUNCED = 15_000;

const MODEL_X = 'newwf-input-model_x';
const MODEL_Y = 'newwf-input-model_y';

type Posted = { inputs?: Record<string, string> };

async function mockPreflight(page: Page): Promise<void> {
  await page.route('**/api/runs/preflight', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        lines: [{ check: 'origin reachable', status: 'ok', text: 'origin ok', fix: null }],
        start_allowed: true,
        queue_note: 'starts immediately',
        rows: null,
        plan_error: null,
      }),
    }),
  );
}

async function probe(page: Page, harness: string, models: string[], delayMs = 0): Promise<void> {
  await page.route(`**/api/harnesses/${harness}/probe`, async (route: Route) => {
    if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, failing_reason: null, models, version: 'v1' }),
    });
  });
}

async function openForm(page: Page, link = LINK): Promise<void> {
  await page.goto(link);
  await expect(page.getByTestId('newwf-note')).not.toBeEmpty({ timeout: DEBOUNCED });
}

function radio(page: Page, harness: string) {
  return page.getByTestId(`newwf-harness-${harness}`).locator('input[type="radio"]');
}

function options(page: Page, testId: string) {
  return page.locator(`select[data-testid="${testId}"] option:not([value=""])`);
}

async function fillRequired(page: Page): Promise<void> {
  await page.getByTestId('newwf-input-branch').fill('b');
  await page.getByTestId('newwf-input-spec_folder').fill('s');
  await page.getByTestId('newwf-input-story_id').fill('1');
}

/** Starts the run against a stubbed 409 and returns the body `POST /runs` received. */
async function startAndCapture(page: Page): Promise<Posted> {
  let posted: Posted | undefined;
  await page.route('**/api/runs', (route: Route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    posted = route.request().postDataJSON() as Posted;
    return route.fulfill({
      status: 409,
      contentType: 'application/problem+json',
      body: JSON.stringify({ type: 'about:blank', title: 'stop', status: 409, detail: 'stop' }),
    });
  });
  await expect(page.getByTestId('newwf-start')).toBeEnabled({ timeout: DEBOUNCED });
  await page.getByTestId('newwf-start').click();
  await expect(page.getByTestId('newwf-start-error')).toBeVisible();
  expect(posted).toBeDefined();
  return posted as Posted;
}

test.describe('New Workflow model-named inputs', () => {
  test('are free text until a harness is picked, then a select; a default the list lacks is not submitted', async ({
    page,
  }) => {
    await mockPreflight(page);
    await probe(page, 'claude', ['m-one', 'm-two']);
    await openForm(page);

    await expect(page.locator(`input[data-testid="${MODEL_X}"]`)).toBeVisible();
    await expect(page.locator(`input[data-testid="${MODEL_Y}"]`)).toHaveValue('not-served');
    await radio(page, 'claude').click();

    await expect(options(page, MODEL_X)).toHaveText(['m-one', 'm-two'], { timeout: DEBOUNCED });
    await expect(options(page, 'newwf-model')).toHaveText(['m-one', 'm-two']);
    await expect(page.locator(`select[data-testid="${MODEL_Y}"] option[value=""]`)).toHaveText(
      '— (template default: not-served)',
    );

    await fillRequired(page);
    expect((await startAndCapture(page)).inputs?.model_y).toBe('');
  });

  test('the chosen value reaches POST /runs and the URL', async ({ page }) => {
    await mockPreflight(page);
    await probe(page, 'claude', ['m-one', 'm-two']);
    await openForm(page);
    await radio(page, 'claude').click();
    await expect(options(page, MODEL_X)).toHaveCount(2, { timeout: DEBOUNCED });
    await page.getByTestId(MODEL_X).selectOption('m-two');
    await fillRequired(page);
    await expect(page.getByTestId('newwf-start')).toBeEnabled({ timeout: DEBOUNCED });
    expect(page.url()).toContain('in_model_x=m-two');

    expect((await startAndCapture(page)).inputs?.model_x).toBe('m-two');
  });

  test('an empty list leaves free text and a value typed before the probe answers survives', async ({
    page,
  }) => {
    await mockPreflight(page);
    await probe(page, 'claude', [], 700);
    await openForm(page);
    const answered = page.waitForResponse('**/api/harnesses/claude/probe');
    await radio(page, 'claude').click();
    await page.getByTestId(MODEL_X).fill('typed');
    await answered;

    await expect(page.locator(`input[data-testid="${MODEL_X}"]`)).toHaveValue('typed');
    await fillRequired(page);
    expect((await startAndCapture(page)).inputs?.model_x).toBe('typed');
  });

  test('ok: false clears the harness and leaves model_y as free text at its default', async ({
    page,
  }) => {
    await mockPreflight(page);
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
    await openForm(page);
    await radio(page, 'claude').click();

    await expect(radio(page, 'claude')).toBeDisabled({ timeout: DEBOUNCED });
    await expect(page.locator(`input[data-testid="${MODEL_Y}"]`)).toHaveValue('not-served');
  });

  for (const failure of ['500', 'abort'] as const) {
    test(`a probe that fails (${failure}) after an earlier success drops the stale list`, async ({
      page,
    }) => {
      await mockPreflight(page);
      let calls = 0;
      await page.route('**/api/harnesses/claude/probe', (route: Route) => {
        calls++;
        if (calls === 1) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              ok: true,
              failing_reason: null,
              models: ['m-one'],
              version: 'v',
            }),
          });
        }
        return failure === '500' ? route.fulfill({ status: 500, body: 'boom' }) : route.abort();
      });
      await openForm(page);
      await radio(page, 'claude').click();
      await expect(options(page, MODEL_X)).toHaveCount(1, { timeout: DEBOUNCED });

      await probe(page, 'codex', ['c-one']);
      await radio(page, 'codex').click();
      await expect(options(page, MODEL_X)).toHaveText(['c-one'], { timeout: DEBOUNCED });
      await radio(page, 'claude').click();

      await expect(page.locator(`input[data-testid="${MODEL_X}"]`)).toBeVisible({
        timeout: DEBOUNCED,
      });
      await expect(radio(page, 'claude')).toBeChecked();
    });
  }

  test('switching harness resets the value; an empty-list harness restores the default as free text', async ({
    page,
  }) => {
    await mockPreflight(page);
    await probe(page, 'claude', ['shared', 'only-claude']);
    await probe(page, 'codex', ['shared', 'only-codex']);
    await probe(page, 'local', []);
    await openForm(page);
    await radio(page, 'claude').click();
    await expect(options(page, MODEL_X)).toHaveCount(2, { timeout: DEBOUNCED });
    await page.getByTestId(MODEL_X).selectOption('shared');

    await radio(page, 'codex').click();
    await expect(options(page, MODEL_X)).toHaveText(['shared', 'only-codex'], {
      timeout: DEBOUNCED,
    });
    await fillRequired(page);
    expect((await startAndCapture(page)).inputs?.model_x).toBe('');

    await radio(page, 'local').click();
    await expect(page.locator(`input[data-testid="${MODEL_Y}"]`)).toHaveValue('not-served', {
      timeout: DEBOUNCED,
    });
  });

  test('a template switched in with a list loaded has its unserved default cleared', async ({
    page,
  }) => {
    await mockPreflight(page);
    await probe(page, 'claude', ['m-one']);
    await openForm(page, base(INITIATIVE_NAME));
    await radio(page, 'claude').click();
    await expect(options(page, 'newwf-model')).toHaveCount(1, { timeout: DEBOUNCED });

    await page.getByTestId('newwf-template').selectOption(STORY_RUN_NAME);
    await expect(options(page, MODEL_Y)).toHaveCount(1);
    await fillRequired(page);
    expect((await startAndCapture(page)).inputs?.model_y).toBe('');
  });
});
