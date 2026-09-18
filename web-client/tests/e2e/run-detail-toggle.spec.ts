/**
 * Run detail toggle (8.1): when RunDetail mounts (no ?view= param), Header receives
 * `view="detail"`, which replaces the `aria-disabled` stub toggle with functional
 * `<a href>` links — including a link to `?view=diagram`.
 *
 * This verifies that RunDetail passes `view="detail"` to Header and that the diagram
 * toggle is a live anchor, not a disabled placeholder.
 */

import { expect, test, type Route } from '@playwright/test';

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939aa';
const BASE_URL = `/workflows/${RUN_ID}`;

function minimalDetail(): Record<string, unknown> {
  return {
    header: {
      meta: {
        project: 'Toggle Test',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'docs',
        template: 'initiative',
        version: 1,
        harness: 'claude',
        started_at: '2026-09-11T09:00:00Z',
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
      created_at: '2026-09-11T09:00:00Z',
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

test.describe('/workflows/[id] (no ?view=) — RunDetail toggle', () => {
  test('diagram toggle is a functional <a> link to ?view=diagram, not aria-disabled', async ({
    page,
  }) => {
    // operator revision 2026-09-18: story 8-3 put `?opened=true` on the first detail fetch; the
    // trailing `**` admits the query string a bare glob never matches. `run-detail-last-opened.
    // spec.ts` AC1/AC3 assert the new behaviour.
    await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(minimalDetail()),
      }),
    );

    await page.goto(BASE_URL);

    await expect(page.getByTestId('wf-header')).toBeVisible();

    // The toggle must contain an <a> link that points at ?view=diagram
    const diagramLink = page.locator('[data-testid="wf-toggle-diagram"] a[href*="view=diagram"]');
    await expect(diagramLink).toBeVisible();

    // No aria-disabled element inside the toggle (the old stub is gone)
    await expect(page.locator('[data-testid="wf-toggle-diagram"] [aria-disabled]')).toHaveCount(0);
  });
});
