import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * Run detail (4.15, SPEC CAP-15, FR-23).
 *
 * `GET /api/runs/{id}/detail` and `POST /api/runs/{id}/signals` are mocked with
 * `page.route()`, the same way `new-workflow.spec.ts` mocks `/runs/preflight` and `/runs`:
 * there is no engine here to walk a real plan, and the ACs are about rendering a given
 * response and posting a given signal, not about producing either.
 *
 * Waiting on `wf-header` is this screen's own hydration gate (`new-workflow.spec.ts`'s
 * `openForm` precedent): the island renders nothing at all until its first fetch resolves,
 * so a visible header only ever appears once `client:load` has actually mounted.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939aa';
const URL = `/workflows/${RUN_ID}`;

const RED = 'rgb(224, 82, 82)';

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'running',
    admitted_signals: [],
    branch: 'epics/1',
    budget_usd: '15.00',
    compare_urls: [],
    created_at: '2026-09-07T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: null,
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '4.18',
    template: 'initiative',
    terminal_session: false,
    version: 1,
    worktree_path: null,
    worktrees: [],
    accepted_paths: [],
    ...overrides,
  };
}

function detail(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    header: {
      meta: {
        project: 'Mixed Signals',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'docs/initiative',
        template: 'initiative',
        version: 1,
        harness: 'claude',
        started_at: '2026-09-07T09:00:05Z',
        worktree_path: '/work/orchestrator',
      },
    },
    alert: null,
    steps: [],
    stories: [],
    cost: {
      spent_usd: '4.18',
      budget_usd: '15.00',
      tokens_in: 1000,
      tokens_out: 2000,
      wall_clock_seconds: 90,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: [],
    summary: null,
    // spread before `run` is resolved, so a caller's own `run` override — a *partial* run
    // object — never clobbers the full one `run()` merges it into below
    ...overrides,
    run: run((overrides.run as Record<string, unknown>) ?? {}),
  };
}

function stepRow(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    seq: 1,
    path: 'row',
    label: 'row',
    kind: 'shell',
    gate: 'deterministic',
    status: 'planned',
    token: 'QUE',
    reason: null,
    attempts: 1,
    latest: null,
    ...overrides,
  };
}

async function mockDetail(page: Page, body: Record<string, unknown>): Promise<void> {
  // operator revision 2026-09-18: story 8-3 put `?opened=true` on the first detail fetch; the
  // trailing `**` admits the query string a bare glob never matches. `run-detail-last-opened.
  // spec.ts` AC1/AC3 assert the new behaviour.
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

test.describe('/workflows/[id] (Run detail)', () => {
  test('lists all 12 planned rows by path, row 5 promoted, no colour but the tokens', async ({
    page,
  }) => {
    const steps = Array.from({ length: 12 }, (_, i) =>
      stepRow({
        seq: i + 1,
        path: `row-${i + 1}`,
        token: i + 1 === 5 ? 'RUN' : 'QUE',
        status: i + 1 === 5 ? 'running' : 'planned',
      }),
    );
    await mockDetail(page, detail({ steps }));
    await page.goto(URL);

    await expect(page.getByTestId('wf-header')).toBeVisible();
    // operator revision 2026-09-18: story 1-4 put the Steps table in a tabbed region whose
    // default panel is GATE, so the table is reached rather than arrived on. The rows and the
    // promotion below are unchanged. `run-detail-tabs.spec.ts` asserts the region itself.
    await page.getByRole('button', { name: 'STEPS' }).click();
    for (let i = 1; i <= 12; i += 1) {
      await expect(page.getByTestId(`wf-step-${i}`)).toContainText(`row-${i}`);
    }
    await expect(page.getByTestId('wf-step-5')).toHaveAttribute('data-current', 'true');
  });

  test('a plan_stale park shows the reason and exactly Continue/Cancel run; Continue posts and the banner clears', async ({
    page,
  }) => {
    await mockDetail(
      page,
      detail({
        run: { status: 'needs_you' },
        alert: { token: 'BLK', reason: 'plan stale: stories.yaml', park_kind: 'plan_stale' },
        steps: [stepRow({ path: 'plan', kind: 'plan.check', status: 'error', token: 'ERR' })],
        gate_record: [
          {
            id: 'g1',
            at: '2026-09-07T09:05:00Z',
            path: 'plan',
            event: 'plan_stale',
            actor: 'machine',
            text: 'plan stale: stories.yaml',
            attempt_n: null,
          },
        ],
        admitted_signals: ['continue', 'cancel'],
      }),
    );
    await page.goto(URL);

    await expect(page.getByTestId('wf-alert')).toContainText('plan stale: stories.yaml');
    await expect(page.getByTestId('wf-signal-continue')).toBeVisible();
    await expect(page.getByTestId('wf-cancel')).toBeVisible();
    await expect(page.getByTestId('wf-signal-retry')).toHaveCount(0);

    let posted: Record<string, unknown> | null = null;
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      posted = route.request().postDataJSON() as Record<string, unknown>;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(run()),
      });
    });
    await mockDetail(
      page,
      detail({
        run: { status: 'running' },
        steps: [stepRow({ path: 'plan', status: 'done', token: 'DON' })],
      }),
    );

    await page.getByTestId('wf-signal-continue').click();

    await expect.poll(() => posted).not.toBeNull();
    expect(posted!.kind).toBe('continue');
    await expect(page.getByTestId('wf-alert')).toHaveCount(0);
  });

  test('a push_rejected park shows the log tail and the resolve line; Retry posts {kind: retry}', async ({
    page,
  }) => {
    await mockDetail(
      page,
      detail({
        run: { status: 'needs_you' },
        alert: {
          token: 'BLK',
          reason: 'push rejected: non-fast-forward',
          park_kind: 'push_rejected',
        },
        steps: [
          stepRow({
            path: 'push',
            kind: 'git.push',
            status: 'error',
            token: 'ERR',
            latest: {
              n: 1,
              started_at: null,
              ended_at: null,
              seconds: null,
              harness: null,
              model: null,
              exit_code: 1,
              cost_usd: null,
              log_tail: ['! [rejected]  main -> main'],
            },
          }),
        ],
        gate_record: [
          {
            id: 'g1',
            at: '2026-09-07T09:05:00Z',
            path: 'push',
            event: 'push_rejected',
            actor: 'machine',
            text: 'push rejected',
            attempt_n: null,
          },
        ],
        admitted_signals: ['retry', 'cancel'],
      }),
    );
    await page.goto(URL);

    await expect(page.getByTestId('wf-stop-push_rejected')).toContainText(
      'resolve on the remote, then Retry',
    );
    await expect(page.getByTestId('wf-stop-push_rejected')).toContainText('[rejected]');

    let posted: Record<string, unknown> | null = null;
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      posted = route.request().postDataJSON() as Record<string, unknown>;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(run()),
      });
    });

    await page.getByTestId('wf-signal-retry').click();

    await expect.poll(() => posted).not.toBeNull();
    expect(posted!.kind).toBe('retry');
  });

  test('Cancel run: confirming posts confirm: true; dismissing posts nothing', async ({ page }) => {
    await mockDetail(
      page,
      detail({
        run: { status: 'needs_you' },
        alert: { token: 'BLK', reason: 'timeout', park_kind: 'timeout' },
        admitted_signals: ['retry', 'cancel'],
      }),
    );
    await page.goto(URL);
    await expect(page.getByTestId('wf-cancel')).toBeVisible();

    let calls = 0;
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      calls += 1;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(run()),
      });
    });

    await page.getByTestId('wf-cancel').click();
    await expect(page.getByTestId('wf-cancel-confirm')).toContainText('cancel run epics/1?');
    await expect(page.getByTestId('wf-cancel-confirm')).toContainText(
      'running processes are killed',
    );

    await page.getByTestId('wf-cancel-confirm-no').click();
    await expect(page.getByTestId('wf-cancel-confirm')).toHaveCount(0);
    expect(calls).toBe(0);

    await page.getByTestId('wf-cancel').click();
    let posted: Record<string, unknown> | null = null;
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      posted = route.request().postDataJSON() as Record<string, unknown>;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(run()),
      });
    });
    await mockDetail(
      page,
      detail({
        run: { status: 'cancelled' },
        gate_record: [
          {
            id: 'g1',
            at: '2026-09-07T10:00:00Z',
            path: null,
            event: 'cancel',
            actor: 'operator',
            text: 'cancelled by the operator',
            attempt_n: null,
          },
        ],
      }),
    );
    await page.getByTestId('wf-cancel-confirm-yes').click();

    await expect.poll(() => posted).not.toBeNull();
    expect((posted!.payload as Record<string, unknown>).confirm).toBe(true);
  });

  test('a failed Run shows the red banner, the log tail, and only the start-a-new-run link', async ({
    page,
  }) => {
    await mockDetail(
      page,
      detail({
        run: { status: 'failed' },
        steps: [
          stepRow({
            path: 'build',
            status: 'error',
            token: 'ERR',
            latest: {
              n: 1,
              started_at: null,
              ended_at: null,
              seconds: null,
              harness: null,
              model: null,
              exit_code: 1,
              cost_usd: null,
              log_tail: ['npm ERR! build failed'],
            },
          }),
        ],
        gate_record: [
          {
            id: 'g1',
            at: '2026-09-07T09:10:00Z',
            path: 'build',
            event: 'failed',
            actor: 'machine',
            text: 'exit 1',
            attempt_n: null,
          },
        ],
        admitted_signals: [],
      }),
    );
    await page.goto(URL);

    await expect(page.getByTestId('wf-alert')).toHaveCSS('border-left-color', RED);
    await expect(page.getByTestId('wf-stop-failed')).toContainText('npm ERR! build failed');
    await expect(page.getByRole('link', { name: 'start a new run' })).toBeVisible();
    await expect(page.getByTestId('wf-cancel')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-retry')).toHaveCount(0);
  });

  test('a done Run with one skipped story and two links reads the summary line, no amber or red pixel', async ({
    page,
  }) => {
    await mockDetail(
      page,
      detail({
        run: { status: 'done' },
        summary: {
          progress: { epics_done: 1, epics_total: 1, stories_done: 3, stories_total: 4, links: 2 },
          links: ['https://github.com/o/r/pull/1', 'https://github.com/o/r/pull/2'],
          skipped: ['4-9'],
        },
        admitted_signals: [],
      }),
    );
    await page.goto(URL);

    await expect(page.getByTestId('wf-summary')).toContainText('1/1 epics');
    await expect(page.getByTestId('wf-summary')).toContainText('skipped: 4-9');
    await expect(page.getByTestId('wf-alert')).toHaveCount(0);

    const signals = await page.evaluate(() => {
      const AMBER = 'rgb(228, 179, 60)';
      const RED_RGB = 'rgb(224, 82, 82)';
      const found: string[] = [];
      for (const element of document.querySelectorAll('*')) {
        const style = getComputedStyle(element);
        for (const property of ['color', 'background-color', 'border-left-color']) {
          const value = style.getPropertyValue(property);
          if (value.includes(AMBER) || value.includes(RED_RGB)) found.push(property);
        }
      }
      return found;
    });
    expect(signals).toEqual([]);
  });

  test('a skipped row reads SKP · skipped — {reason}, grey', async ({ page }) => {
    await mockDetail(
      page,
      detail({
        steps: [
          stepRow({
            path: 'verify',
            status: 'skipped',
            token: 'SKP',
            reason: 'no quality_gate_command',
          }),
        ],
      }),
    );
    await page.goto(URL);

    // operator revision 2026-09-18: story 1-4 put the Steps table behind the STEPS tab; the
    // row's own reading below is unchanged. See `run-detail-tabs.spec.ts`.
    await page.getByRole('button', { name: 'STEPS' }).click();
    await expect(page.getByTestId('wf-step-1')).toContainText(
      'SKP · skipped — no quality_gate_command',
    );
  });

  test('a failed fetch renders the full-surface readout; Retry restores the screen', async ({
    page,
  }) => {
    let fail = true;
    // operator revision 2026-09-18: story 8-3 put `?opened=true` on the first detail fetch; the
    // trailing `**` admits the query string a bare glob never matches. `run-detail-last-opened.
    // spec.ts` AC1/AC3 assert the new behaviour.
    await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) => {
      if (fail) {
        return route.fulfill({
          status: 500,
          contentType: 'application/problem+json',
          body: JSON.stringify({ type: 'about:blank', title: 'error', status: 500 }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(detail()),
      });
    });
    await page.goto(URL);

    await expect(page.getByTestId('fetch-failed')).toBeVisible();
    await expect(page.getByTestId('fetch-failed')).toContainText(`GET /api/runs/${RUN_ID}/detail`);

    fail = false;
    await page.getByTestId('fetch-retry').click();

    await expect(page.getByTestId('wf-header')).toBeVisible();
  });
});
