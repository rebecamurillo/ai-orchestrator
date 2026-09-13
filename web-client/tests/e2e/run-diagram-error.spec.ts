/**
 * Run diagram view (8.1) — graph fetch error handling.
 *
 * Covers the I/O matrix row: "Graph fetch error — FailedFetch with Retry; polling stopped;
 * Retry handler calls fetchGraph again."
 */

import { expect, test, type Route } from '@playwright/test';

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939ab';
const BASE_URL = `/workflows/${RUN_ID}`;
const DIAGRAM_URL = `${BASE_URL}?view=diagram`;

function minimalDetail(): Record<string, unknown> {
  return {
    header: {
      meta: {
        project: 'Err Test',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'docs',
        template: 'initiative',
        version: 1,
        harness: 'claude',
        started_at: '2026-09-11T10:00:00Z',
        worktree_path: null,
      },
    },
    alert: null,
    steps: [],
    stories: [],
    cost: {
      spent_usd: '0.00',
      budget_usd: '10.00',
      tokens_in: 0,
      tokens_out: 0,
      wall_clock_seconds: 0,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: ['cancel'],
    summary: null,
    run: {
      id: RUN_ID,
      status: 'running',
      admitted_signals: ['cancel'],
      branch: 'epics/8',
      budget_usd: '10.00',
      compare_urls: [],
      created_at: '2026-09-11T10:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: '11111111-1111-1111-1111-111111111111',
      repository: '22222222-2222-2222-2222-222222222222',
      spend_usd: '0.00',
      template: 'initiative',
      terminal_session: false,
      version: 1,
      worktree_path: null,
      worktrees: [],
      accepted_paths: [],
    },
  };
}

function minimalGraph(): Record<string, unknown> {
  return {
    nodes: [
      {
        id: 'root',
        kind: 'plan.check',
        label: 'root',
        gate: null,
        agent: false,
        human: false,
        call: null,
        status: 'running',
        token: 'RUN',
        current: true,
      },
    ],
    edges: [],
    groups: [],
  };
}

test.describe('/workflows/[id]?view=diagram — graph fetch error', () => {
  test('graph fetch error shows fetch-failed; retry re-calls /graph and clears the error', async ({
    page,
  }) => {
    let graphCallCount = 0;

    await page.route(`**/api/runs/${RUN_ID}/detail`, (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(minimalDetail()),
      }),
    );

    await page.route(`**/api/runs/${RUN_ID}/graph`, async (route: Route) => {
      graphCallCount++;
      if (graphCallCount === 1) {
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'service unavailable' }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(minimalGraph()),
        });
      }
    });

    await page.goto(DIAGRAM_URL);

    // Error state: FailedFetch rendered, wf-diagram absent, polling stopped
    await expect(page.locator('[data-testid="fetch-failed"]')).toBeVisible();
    await expect(page.locator('[data-testid="wf-diagram"]')).not.toBeVisible();
    expect(graphCallCount).toBe(1);

    // Click retry — handler calls fetchGraph (and fetchDetail) again
    await page.locator('[data-testid="fetch-retry"]').click();

    // Retry must have issued a second /graph request
    await expect(async () => {
      expect(graphCallCount).toBeGreaterThan(1);
    }).toPass({ timeout: 5000 });

    // Error cleared after successful retry, diagram visible
    await expect(page.locator('[data-testid="fetch-failed"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="wf-diagram"]')).toBeVisible({ timeout: 5000 });
  });
});
