import { expect, test, type Page, type Route } from '@playwright/test';

import { MIXED_ID, MIXED_OK_REPO_ID } from './projects-fixtures.mjs';
import { INITIATIVE_NAME } from './templates-fixtures.mjs';

/**
 * Probe-form flow for the New Workflow screen (story 2-3, probe-based harness gating).
 *
 * All API calls are mocked with `page.route()` — the same pattern `new-workflow.spec.ts`
 * uses for `POST /runs/preflight` and `POST /runs`.  The stub backend has no
 * `GET /api/v1/harnesses/{name}/probe` route, so every probe call in these specs is
 * fulfilled by a mock installed before the action that triggers it.
 */

const LINK = `/workflows/new?template=${INITIATIVE_NAME}&project=${MIXED_ID}&repository=${MIXED_OK_REPO_ID}&branch=main`;
const RUN_ID = '01930000-0000-7000-8000-000000000001';

/** Default 5 s is thin when this file runs beside CPU-heavy specs. */
const DEBOUNCED = 15_000;

function preflightOk(): Record<string, unknown> {
  return {
    lines: [{ check: 'origin reachable', status: 'ok', text: 'origin ok', fix: null }],
    start_allowed: true,
    queue_note: 'starts immediately',
    rows: null,
    plan_error: null,
  };
}

function probeOkBody(models = ['claude-opus-4', 'claude-sonnet-4']): Record<string, unknown> {
  return { ok: true, failing_reason: null, models, version: 'v1.2.3' };
}

function probeFailBody(reason = 'not logged in'): Record<string, unknown> {
  return { ok: false, failing_reason: reason, models: [], version: '' };
}

async function mockPreflight(page: Page): Promise<void> {
  await page.route('**/api/runs/preflight', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(preflightOk()),
    }),
  );
}

/** Open the form and wait for the island to mount (queue note non-empty). */
async function openForm(page: Page): Promise<void> {
  await page.goto(LINK);
  await expect(page.getByTestId('newwf-note')).not.toBeEmpty({ timeout: DEBOUNCED });
}

test.describe('New Workflow probe-based harness gating', () => {
  test('harness radio is initially enabled regardless of HarnessOut.enabled (Operator decision 2026-09-17)', async ({
    page,
  }) => {
    await mockPreflight(page);
    await openForm(page);

    // On first load no probe has been run — the radio must be selectable
    const radio = page.getByTestId('newwf-harness-claude').locator('input[type="radio"]');
    await expect(radio).toBeEnabled();
  });

  test('harness selected, probe ok: radio stays checked and model select shows probed models', async ({
    page,
  }) => {
    await mockPreflight(page);
    await page.route('**/api/harnesses/claude/probe', (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(probeOkBody(['claude-opus-4', 'claude-sonnet-4'])),
      }),
    );
    await openForm(page);

    const radio = page.getByTestId('newwf-harness-claude').locator('input[type="radio"]');
    await radio.click();

    // Model select (a <select> element) must appear with the probed model options.
    // The select always has a blank placeholder option; `:not([value=""])` counts only the
    // probed models so the assertion doesn't depend on the placeholder.
    await expect(page.locator('[data-testid="newwf-model"] option:not([value=""])')).toHaveCount(
      2,
      { timeout: DEBOUNCED },
    );
    await expect(radio).toBeChecked();
    await expect(radio).not.toBeDisabled();
  });

  test('harness selected, probe fail: radio disabled, row shows failing_reason, Start disabled', async ({
    page,
  }) => {
    await mockPreflight(page);
    await page.route('**/api/harnesses/claude/probe', (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(probeFailBody('not logged in')),
      }),
    );
    await openForm(page);

    const claudeRow = page.getByTestId('newwf-harness-claude');
    await claudeRow.locator('input[type="radio"]').click();

    await expect(claudeRow.locator('input[type="radio"]')).toBeDisabled({ timeout: DEBOUNCED });
    await expect(claudeRow).toContainText('not logged in');
    await expect(page.getByTestId('newwf-start')).toBeDisabled();
  });

  test('non-harness field change does not call probe endpoint', async ({ page }) => {
    await mockPreflight(page);
    let probeCalls = 0;
    await page.route('**/api/harnesses/*/probe', (route: Route) => {
      probeCalls++;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(probeOkBody()),
      });
    });
    await openForm(page);

    // Change a non-harness field and wait for the debounced preflight to fire
    await page.getByTestId('newwf-budget').fill('100');
    await expect(page.getByTestId('newwf-start')).toBeEnabled({ timeout: DEBOUNCED });

    expect(probeCalls).toBe(0);
  });

  test('Start clicked with passing submit-time probe calls POST /runs', async ({ page }) => {
    await mockPreflight(page);
    await page.route('**/api/harnesses/claude/probe', (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(probeOkBody()),
      }),
    );
    await openForm(page);

    // Select harness and wait for probe to succeed
    await page.getByTestId('newwf-harness-claude').locator('input[type="radio"]').click();
    await expect(
      page.getByTestId('newwf-harness-claude').locator('input[type="radio"]'),
    ).toBeChecked({ timeout: DEBOUNCED });

    // Fill required budget field
    await page.getByTestId('newwf-budget').fill('50');
    await expect(page.getByTestId('newwf-start')).toBeEnabled({ timeout: DEBOUNCED });

    await page.route('**/api/runs', (route: Route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          run: {
            id: RUN_ID,
            status: 'queued',
            template: 'initiative',
            version: 1,
            project: MIXED_ID,
            repository: MIXED_OK_REPO_ID,
            branch: 'main',
            budget_usd: '50',
            spend_usd: '0',
            plan_ref: null,
            created_at: '2026-09-17T10:00:00Z',
            admitted_signals: [],
          },
          starts_now: true,
          waiting: '',
        }),
      });
    });

    await page.getByTestId('newwf-start').click();

    // Page navigates to run detail on success
    await expect(page).toHaveURL(`/workflows/${RUN_ID}`, { timeout: DEBOUNCED });
  });

  test('Start clicked with failing submit-time probe: POST /runs not called, PRE-FLIGHT shows HARNESS fail', async ({
    page,
  }) => {
    await mockPreflight(page);
    let probeCallCount = 0;
    await page.route('**/api/harnesses/claude/probe', (route: Route) => {
      probeCallCount++;
      // First call: harness selection — ok, so harness stays selected
      // Subsequent calls: submit-time probe — fail
      const body = probeCallCount === 1 ? probeOkBody() : probeFailBody('gateway unreachable');
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });

    await openForm(page);

    // Select harness — first probe fires (ok)
    await page.getByTestId('newwf-harness-claude').locator('input[type="radio"]').click();
    await expect(
      page.getByTestId('newwf-harness-claude').locator('input[type="radio"]'),
    ).toBeChecked({ timeout: DEBOUNCED });

    // Fill budget to enable Start
    await page.getByTestId('newwf-budget').fill('50');
    await expect(page.getByTestId('newwf-start')).toBeEnabled({ timeout: DEBOUNCED });

    let runPostCalled = false;
    await page.route('**/api/runs', (route: Route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      runPostCalled = true;
      return route.fulfill({ status: 500 });
    });

    await page.getByTestId('newwf-start').click();

    // Submit-time probe fails — PRE-FLIGHT must show the HARNESS fail line
    const harnessPreflight = page.getByTestId('newwf-preflight-harness');
    await expect(harnessPreflight).toContainText('gateway unreachable', { timeout: DEBOUNCED });
    await expect(harnessPreflight).toContainText('x');
    // POST /runs must not have been called
    expect(runPostCalled).toBe(false);
    // Start remains disabled because start_allowed is false
    await expect(page.getByTestId('newwf-start')).toBeDisabled();
  });

  test('probe ok with models=[]: model field stays free-text input (gateway disabled)', async ({
    page,
  }) => {
    await mockPreflight(page);
    await page.route('**/api/harnesses/claude/probe', (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, failing_reason: null, models: [], version: 'v1.2.3' }),
      }),
    );
    await openForm(page);

    await page.getByTestId('newwf-harness-claude').locator('input[type="radio"]').click();
    // Wait for probe to resolve — row text changes from "disabled: …" to "ok"
    await expect(page.getByTestId('newwf-harness-claude')).toContainText('ok', {
      timeout: DEBOUNCED,
    });

    // models=[] → NewWorkflowFields renders a text input, never a select
    await expect(page.locator('input[data-testid="newwf-model"]')).toBeVisible();
    await expect(page.locator('[data-testid="newwf-model"] option:not([value=""])')).toHaveCount(0);
  });

  test('probe in-flight: Start button is disabled', async ({ page }) => {
    await mockPreflight(page);
    let resolveProbe!: () => void;
    await page.route('**/api/harnesses/claude/probe', async (route: Route) => {
      await new Promise<void>((resolve) => {
        resolveProbe = resolve;
      });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(probeOkBody()),
      });
    });
    await openForm(page);

    await page.getByTestId('newwf-harness-claude').locator('input[type="radio"]').click();

    // probeInFlight=true is set synchronously before the first await in runProbe; React flushes
    // it in the same batch as the click handler, so Start must be disabled right away
    await expect(page.getByTestId('newwf-start')).toBeDisabled({ timeout: 2_000 });

    resolveProbe(); // release so the page can unmount cleanly
  });

  test('race guard: rapid harness switches discard the superseded probe result', async ({
    page,
  }) => {
    await mockPreflight(page);
    let resolveClaudeProbe!: () => void;
    await page.route('**/api/harnesses/claude/probe', async (route: Route) => {
      await new Promise<void>((resolve) => {
        resolveClaudeProbe = resolve;
      });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          failing_reason: null,
          models: ['claude-opus-4'],
          version: 'v1',
        }),
      });
    });
    await page.route('**/api/harnesses/codex/probe', (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          failing_reason: null,
          models: ['codex-model'],
          version: 'v1',
        }),
      }),
    );
    await openForm(page);

    // Click claude first (slow probe stays in-flight), then immediately codex
    // (increments probeSeqRef so claude's eventual response is discarded)
    await page.getByTestId('newwf-harness-claude').locator('input[type="radio"]').click();
    await page.getByTestId('newwf-harness-codex').locator('input[type="radio"]').click();

    // Wait for codex probe to resolve — its model appears in the select
    await expect(page.locator('[data-testid="newwf-model"] option:not([value=""])')).toHaveCount(
      1,
      { timeout: DEBOUNCED },
    );

    // Release claude's held probe — seq is stale, result must be discarded
    resolveClaudeProbe();
    // Brief wait to allow a stale update to land (it must not)
    await page.waitForTimeout(300);

    // Model select must show codex's model only, never claude's
    await expect(page.locator('[data-testid="newwf-model"] option:not([value=""])')).toHaveCount(1);
    await expect(
      page.locator('[data-testid="newwf-model"] option:not([value=""])').first(),
    ).toContainText('codex-model');
    // Asserted on the select rather than on `option`: with a plain string, Playwright's
    // `toContainText` requires the locator to resolve to one element, and `option` resolves to
    // the placeholder and the model both — the assertion below raised a strict-mode violation
    // rather than ever checking anything. The select is the one element that holds every option.
    await expect(page.getByTestId('newwf-model')).not.toContainText('claude-opus-4');
  });

  test('submit without harness selected skips probe and calls POST /runs with harness null', async ({
    page,
  }) => {
    await mockPreflight(page);
    let probeCalls = 0;
    await page.route('**/api/harnesses/*/probe', (route: Route) => {
      probeCalls++;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(probeOkBody()),
      });
    });

    let capturedHarness: unknown = 'NOT_SET';
    await page.route('**/api/runs', (route: Route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      const body = JSON.parse(route.request().postData() ?? '{}') as { harness: unknown };
      capturedHarness = body.harness;
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          run: {
            id: RUN_ID,
            status: 'queued',
            template: 'initiative',
            version: 1,
            project: MIXED_ID,
            repository: MIXED_OK_REPO_ID,
            branch: 'main',
            budget_usd: '50',
            spend_usd: '0',
            plan_ref: null,
            created_at: '2026-09-17T10:00:00Z',
            admitted_signals: [],
          },
          starts_now: true,
          waiting: '',
        }),
      });
    });

    await openForm(page);
    await page.getByTestId('newwf-budget').fill('50');
    await expect(page.getByTestId('newwf-start')).toBeEnabled({ timeout: DEBOUNCED });

    await page.getByTestId('newwf-start').click();
    await expect(page).toHaveURL(`/workflows/${RUN_ID}`, { timeout: DEBOUNCED });

    expect(probeCalls).toBe(0);
    expect(capturedHarness).toBeNull();
  });
});
