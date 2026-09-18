import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * The Runs screen's HISTORY section (7.5, SPEC CAP-5, FR-25 history, UX-DR14), and the
 * `#step-{seq}` arrival on the Run detail it links to.
 *
 * `GET /api/v1/steps` answers unconditionally empty in the shared stub (`stub-backend.mjs`,
 * `GET /api/v1/queue`'s own precedent), so every real-content scenario here mocks
 * `GET /api/steps` with `page.route()` instead — there is nothing here that has ever
 * executed, and the ACs are about rendering a given response.
 *
 * `openHistory` waits on `runs-history` as its hydration gate: the island renders nothing at
 * all until its first fetch resolves (`RunsQueue.tsx`'s own pattern), and that element wraps
 * the section head, the table, the empty reading and the failed read alike, so it is the one
 * element every ready state shares.
 *
 * The queue is mocked empty throughout: this file is about the section below it, and leaving
 * the queue on the stub keeps each scenario to the one endpoint it is actually asserting on.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939aa';
const PROJECT_ID = '55555555-5555-5555-5555-555555555555';
const GREEN = 'rgb(79, 180, 119)';

function historyRow(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    attempt_id: '00000000-0000-0000-0000-000000000001',
    run_id: RUN_ID,
    seq: 7,
    started_at: '2026-09-09T08:04:05Z',
    ended_at: '2026-09-09T08:06:35Z',
    seconds: 150,
    project_name: 'Mixed Signals',
    run_label: 'story v3 · feat/epic-7',
    path: 'epics[0].stories[3].build',
    kind: 'agent',
    harness: 'codex',
    model: 'gpt-5-codex',
    session_id: 'sess-1',
    status: 'done',
    token: 'DON',
    tokens_in: 100,
    tokens_out: 20,
    cost_usd: '0.250000',
    cost_provisional: false,
    trace_url: 'https://langfuse.test/traces/1',
    log_tail_url: `/api/v1/runs/${RUN_ID}/detail`,
    ...overrides,
  };
}

/** Answers `GET /api/steps` from a queue of responses, recording the URL of each request —
 * which is how the filter and the *more* cursor are asserted as *requests*, not as renders. */
async function mockHistory(
  page: Page,
  pages: Record<string, unknown>[],
  seen: string[] = [],
): Promise<string[]> {
  let at = 0;
  await page.route('**/api/steps*', (route: Route) => {
    seen.push(route.request().url());
    const body = pages[Math.min(at, pages.length - 1)]!;
    at += 1;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });
  return seen;
}

async function mockQueueEmpty(page: Page): Promise<void> {
  await page.route('**/api/queue*', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], next_cursor: null, max_active_runs: 2 }),
    }),
  );
}

async function openHistory(page: Page, url: string = '/runs'): Promise<void> {
  await mockQueueEmpty(page);
  await page.goto(url);
  await expect(page.getByTestId('runs-history')).toBeVisible();
}

test.describe('/runs (HISTORY section)', () => {
  test('the section head is the word HISTORY and the table carries UX-DR14’s ten columns', async ({
    page,
  }) => {
    await mockHistory(page, [{ items: [historyRow()], next_cursor: null }]);
    await openHistory(page);

    await expect(page.getByTestId('runs-history')).toContainText('HISTORY');
    await expect(page.getByTestId('runs-history')).not.toContainText(
      'history arrives with the harness comparison epic',
    );

    const heads = page.getByTestId('runs-history').locator('thead th');
    await expect(heads).toHaveCount(10);
    await expect(heads).toHaveText([
      'time',
      'project',
      'workflow',
      'path',
      'kind',
      'harness',
      'status',
      'time',
      'cost',
      'trace',
    ]);
  });

  test('an agent row reads every column; a non-agent row reads em dashes where it has nothing', async ({
    page,
  }) => {
    await mockHistory(page, [
      {
        items: [
          historyRow(),
          historyRow({
            attempt_id: '00000000-0000-0000-0000-000000000002',
            seq: 8,
            kind: 'git.commit',
            path: 'epics[0].stories[3].commit',
            harness: null,
            model: null,
            session_id: null,
            tokens_in: null,
            tokens_out: null,
            cost_usd: null,
            trace_url: null,
          }),
        ],
        next_cursor: null,
      },
    ]);
    await openHistory(page);

    const agent = page.getByTestId('runs-history-row-00000000-0000-0000-0000-000000000001');
    await expect(agent).toContainText('08:04:05');
    await expect(agent).toContainText('Mixed Signals');
    await expect(agent).toContainText('story v3 · feat/epic-7');
    await expect(agent).toContainText('epics[0].stories[3].build');
    await expect(agent).toContainText('agent');
    await expect(agent).toContainText('codex · gpt-5-codex');
    await expect(agent).toContainText('DON');
    await expect(agent).toContainText('150s');
    await expect(agent).toContainText('$0.250000');
    await expect(agent.getByRole('link', { name: 'trace' })).toHaveAttribute(
      'href',
      'https://langfuse.test/traces/1',
    );

    const git = page.getByTestId('runs-history-row-00000000-0000-0000-0000-000000000002');
    await expect(git).toContainText('git.commit');
    await expect(git.locator('td', { hasText: /^—$/ })).toHaveCount(3);
  });

  test('the status token is the only coloured cell in a row', async ({ page }) => {
    await mockHistory(page, [
      {
        items: [historyRow({ status: 'running', token: 'RUN', seconds: null, ended_at: null })],
        next_cursor: null,
      },
    ]);
    await openHistory(page);

    const row = page.getByTestId('runs-history-row-00000000-0000-0000-0000-000000000001');
    await expect(row.locator('.runs-history-token')).toHaveCSS('color', GREEN);
    const cells = row.locator('td');
    for (let at = 0; at < (await cells.count()); at += 1) {
      const colour = await cells.nth(at).evaluate((cell) => getComputedStyle(cell).color);
      expect(colour).not.toBe(GREEN);
    }
  });

  test('clicking a row navigates to the Run detail scrolled to that step, promoted on arrival', async ({
    page,
  }) => {
    await mockHistory(page, [{ items: [historyRow({ seq: 7 })], next_cursor: null }]);
    // operator revision 2026-09-18: story 8-3 put `?opened=true` on the first detail fetch; the
    // trailing `**` admits the query string a bare glob never matches. `run-detail-last-opened.
    // spec.ts` AC1/AC3 assert the new behaviour.
    await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(detailWithTwentyRows()),
      }),
    );
    await openHistory(page);

    await page
      .getByTestId('runs-history-row-00000000-0000-0000-0000-000000000001')
      .getByRole('link', { name: 'epics[0].stories[3].build' })
      .click();

    await expect(page).toHaveURL(new RegExp(`/workflows/${RUN_ID}#step-7$`));
    await expect(page.getByTestId('wf-header')).toBeVisible();
    await expect(page.getByTestId('wf-step-7')).toHaveAttribute('data-anchored', 'true');
    await expect(page.getByTestId('wf-step-7')).toBeInViewport();
    // "promoted briefly": the promotion clears itself, it is not a permanent state
    await expect(page.getByTestId('wf-step-7')).toHaveAttribute('data-anchored', 'false', {
      timeout: 15_000,
    });
  });

  test('opening the detail directly at #step-7 scrolls to row 7 and promotes it', async ({
    page,
  }) => {
    // operator revision 2026-09-18: story 8-3 put `?opened=true` on the first detail fetch; the
    // trailing `**` admits the query string a bare glob never matches. `run-detail-last-opened.
    // spec.ts` AC1/AC3 assert the new behaviour.
    await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(detailWithTwentyRows()),
      }),
    );

    await page.goto(`/workflows/${RUN_ID}#step-7`);

    await expect(page.getByTestId('wf-header')).toBeVisible();
    await expect(page.getByTestId('wf-step-7')).toHaveAttribute('data-anchored', 'true');
    await expect(page.getByTestId('wf-step-7')).toBeInViewport();
    await expect(page.getByTestId('wf-step-1')).toHaveAttribute('data-anchored', 'false');
  });

  test('more appends the next page and then reads the end', async ({ page }) => {
    const seen = await mockHistory(page, [
      { items: [historyRow()], next_cursor: 'CURSOR-1' },
      {
        items: [historyRow({ attempt_id: '00000000-0000-0000-0000-000000000002', seq: 8 })],
        next_cursor: null,
      },
    ]);
    await openHistory(page);

    await expect(page.getByTestId('runs-history').locator('tbody tr')).toHaveCount(1);
    await page.getByTestId('runs-history-more').click();

    await expect(page.getByTestId('runs-history').locator('tbody tr')).toHaveCount(2);
    expect(seen[1]).toContain('cursor=CURSOR-1');
    // the last page carried no cursor, so the control is replaced by the reading
    await expect(page.getByTestId('runs-history-more')).toHaveCount(0);
    await expect(page.getByTestId('runs-history')).toContainText('no more attempts');
  });

  test('the bar’s project and status filters reach the history request, and the queue ignores them', async ({
    page,
  }) => {
    const seen = await mockHistory(page, [{ items: [], next_cursor: null }]);
    let queueUrl = '';
    await page.route('**/api/queue*', (route: Route) => {
      queueUrl = route.request().url();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], next_cursor: null, max_active_runs: 2 }),
      });
    });

    await page.goto(`/runs?project=${PROJECT_ID}&status=BLK`);
    await expect(page.getByTestId('runs-history')).toBeVisible();

    expect(seen[0]).toContain(`project_id=${PROJECT_ID}`);
    expect(seen[0]).toContain('status=BLK');
    // the queue section takes no query parameters at all (4.16, AD-12)
    expect(queueUrl).not.toContain('project');
    expect(queueUrl).not.toContain('status');
  });

  test('a history with nothing in it reads its own empty state, not the queue’s', async ({
    page,
  }) => {
    await mockHistory(page, [{ items: [], next_cursor: null }]);
    await openHistory(page);

    await expect(page.getByTestId('runs-history-empty')).toContainText('NO ATTEMPTS');
    await expect(page.getByTestId('runs-history-empty')).toContainText('nothing has executed yet');
    // `runs-empty` belongs to the queue section alone (`shell.spec.ts`, frozen)
    await expect(page.getByTestId('runs-empty')).toHaveCount(1);
  });

  test('a failed history read shows its own readout with the request it made; Retry restores it', async ({
    page,
  }) => {
    let fail = true;
    await mockQueueEmpty(page);
    await page.route('**/api/steps*', (route: Route) => {
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
        body: JSON.stringify({ items: [historyRow()], next_cursor: null }),
      });
    });

    await page.goto('/runs');

    const failed = page.getByTestId('runs-history-failed');
    await expect(failed).toBeVisible();
    await expect(failed).toContainText('GET /api/steps');
    await expect(failed).toContainText('500');

    fail = false;
    await failed.getByTestId('fetch-retry').click();

    await expect(page.getByTestId('runs-history-failed')).toHaveCount(0);
    await expect(
      page.getByTestId('runs-history-row-00000000-0000-0000-0000-000000000001'),
    ).toBeVisible();
  });
});

/** A Run detail with twenty rows, so row 7 is genuinely below the fold before the scroll. */
function detailWithTwentyRows(): Record<string, unknown> {
  return {
    header: {
      meta: {
        project: 'Mixed Signals',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'docs/initiative',
        template: 'story',
        version: 3,
        harness: 'codex',
        started_at: '2026-09-09T08:00:00Z',
        worktree_path: null,
      },
    },
    alert: null,
    steps: Array.from({ length: 20 }, (_, at) => ({
      seq: at + 1,
      path: `epics[0].stories[${at}].build`,
      label: `row ${at + 1}`,
      kind: 'agent',
      gate: 'deterministic',
      status: 'done',
      token: 'DON',
      reason: null,
      attempts: 1,
      latest: null,
      cost_usd: '0',
    })),
    stories: [],
    cost: {
      spent_usd: '0',
      budget_usd: '15.00',
      tokens_in: 0,
      tokens_out: 0,
      wall_clock_seconds: 0,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: [],
    summary: null,
    run: {
      id: RUN_ID,
      status: 'running',
      admitted_signals: [],
      branch: 'feat/epic-7',
      budget_usd: '15.00',
      compare_urls: [],
      created_at: '2026-09-09T08:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: PROJECT_ID,
      repository: '22222222-2222-2222-2222-222222222222',
      spend_usd: '0',
      template: 'story',
      terminal_session: false,
      version: 3,
      worktree_path: null,
      worktrees: [],
      accepted_paths: [],
    },
  };
}
