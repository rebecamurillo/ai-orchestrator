/**
 * Run detail toggle: when RunDetail mounts (no ?view= param), Header receives
 * `view={undefined}` and renders DIAGRAM as a disabled stub and DETAIL as aria-current.
 * ?view=diagram is retired (FR-29, story 1-4, 2026-09-16); no functional link to it exists.
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
  // Revised: story 1-4 (2026-09-16) — RunDetail passes view={undefined}; DIAGRAM is a disabled stub (FR-29)
  test('diagram toggle renders DIAGRAM as aria-disabled stub and DETAIL as aria-current', async ({
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

    // DIAGRAM is a disabled stub — ?view=diagram is retired (FR-29, story 1-4, 2026-09-16)
    await expect(
      page.locator('[data-testid="wf-toggle-diagram"] [aria-disabled="true"]'),
    ).toHaveText('DIAGRAM');
    // Exactly one aria-disabled element in the toggle
    await expect(page.locator('[data-testid="wf-toggle-diagram"] [aria-disabled]')).toHaveCount(1);
    // DETAIL carries aria-current
    await expect(
      page.locator('[data-testid="wf-toggle-diagram"] [aria-current="true"]'),
    ).toHaveText('DETAIL');
  });
});
