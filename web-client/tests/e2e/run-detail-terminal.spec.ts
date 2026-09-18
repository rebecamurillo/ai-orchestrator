import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * The terminal resume block in a real browser (6.7, FR-21, UX-DR5, UX-DR9).
 *
 * The click is the half no unit test can reach: `vitest.config.ts` runs in
 * `environment: 'node'` with no DOM, so `run-command-block.test.ts` asserts only the first
 * render. Everything below is about what a click does — what lands on the clipboard, what the
 * button reads for the 1.2 s after it, and what gets posted.
 *
 * New file, for the reason `run-detail-accept.spec.ts` gives: the specs before it are frozen
 * and predate this stop. `GET /api/runs/{id}/detail` and `POST /api/runs/{id}/signals` are
 * mocked with `page.route()` — there is no engine here to park a real Run on a resumable
 * claude session, and every assertion is about what the screen does with a given response.
 *
 * **Two of these are security assertions.** AD-5 forbids a secret value on screen, and the
 * proof lives on both sides of the boundary: `backend-api/tests/unit/test_terminal_command.py`
 * proves none can enter the string, and `no secret value reaches the page` below proves the
 * page renders what it was given and expands nothing — a `$LITELLM_API_KEY` in the rendered
 * text and on the clipboard is a reference the *container* resolves, never a value.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939ce';
const URL = `/workflows/${RUN_ID}`;

const STORY_ID = '4-1';
const BUILD = 'epics[0].stories[0].build';
const SESSION = '1f0a0d3c-8b17-4a9e-9c2b-2d4e6f8a0b1c';
const WORKTREE = '/work/acme/orchestrator/wt/epics-1';
const ENDS_AT = '2026-10-07T09:00:00Z';

/** The command as the backend builds it: identifiers inline, credentials by shell name. */
const COMMAND =
  'docker compose exec -e ORCH_RUN_ID=01a06887 -e ORCH_ATTEMPT_ID=01a06888 ' +
  `-e ORCH_STORY_ID=${STORY_ID} -e ORCH_HARNESS=claude -e ORCH_PROJECT=acme ` +
  '-e ORCH_TAGS=run:01a06887,attempt:01a06888 ' +
  `-e ORCH_LANGFUSE_TAGS='["run:01a06887"]' -e TRACEPARENT=00-abc-def-01 ` +
  'backend-api sh -c \'export ANTHROPIC_AUTH_TOKEN="$LITELLM_API_KEY"; ' +
  `cd ${WORKTREE} && claude --resume ${SESSION}'`;

const SESSION_LINE =
  'terminal session in progress · Answer, Continue, Skip and Retry disabled until Release';

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'needs_you',
    admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'],
    branch: 'epics/1',
    budget_usd: '40.00',
    compare_urls: [],
    created_at: '2026-09-07T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: null,
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '4.18',
    template: 'epic',
    terminal_session: false,
    terminal: { command: COMMAND, session_lifetime_ends_at: ENDS_AT, in_progress: false },
    version: 1,
    worktree_path: WORKTREE,
    worktrees: [],
    accepted_paths: [],
    ...overrides,
  };
}

function detail(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    header: {
      meta: {
        project: 'Acme',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'specs/gates',
        template: 'epic',
        version: 1,
        harness: 'claude',
        started_at: '2026-09-07T09:00:05Z',
        worktree_path: WORKTREE,
      },
    },
    alert: {
      token: 'BLK',
      reason: 'Which database migration tool should this use?',
      park_kind: 'blocked',
      row_kind: 'agent',
      payload: {},
    },
    steps: [
      {
        seq: 1,
        path: BUILD,
        label: 'build',
        kind: 'agent',
        gate: 'liveness',
        status: 'blocked',
        token: 'BLK',
        reason: 'intent gap',
        attempts: 1,
        latest: null,
      },
    ],
    stories: [{ epic_index: 0, story_id: STORY_ID, state: 'current', cost_usd: '4.18' }],
    cost: {
      spent_usd: '4.18',
      budget_usd: '40.00',
      tokens_in: 15000,
      tokens_out: 4200,
      wall_clock_seconds: 930,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'],
    summary: null,
    ...overrides,
    run: run((overrides.run as Record<string, unknown>) ?? {}),
  };
}

/** The Run as it stands once `terminal_start` has been applied: the server drops every other
 * action and marks the session (`application/rules/signals.py::run_admitted_signals`). */
function inSessionDetail(): Record<string, unknown> {
  return detail({
    admitted_signals: ['cancel', 'terminal_release'],
    run: {
      admitted_signals: ['cancel', 'terminal_release'],
      terminal_session: true,
      terminal: { command: COMMAND, session_lifetime_ends_at: ENDS_AT, in_progress: true },
    },
  });
}

async function mockDetail(page: Page, body: Record<string, unknown>): Promise<void> {
  // operator revision 2026-09-18: story 8-3 put `?opened=true` on the first detail fetch; the
  // trailing `**` admits the query string a bare glob never matches. `run-detail-last-opened.
  // spec.ts` AC1/AC3 assert the new behaviour.
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

async function open(page: Page, body = detail()): Promise<void> {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await mockDetail(page, body);
  await page.goto(URL);
  await expect(page.getByTestId('wf-header')).toBeVisible();
}

function collect(page: Page, answer: Record<string, unknown>): Record<string, unknown>[] {
  const posted: Record<string, unknown>[] = [];
  void page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
    posted.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(answer),
    });
  });
  return posted;
}

test.describe('the command block', () => {
  test('shows the command and the date the session stops being resumable', async ({ page }) => {
    await open(page);

    await expect(page.getByTestId('wf-terminal')).toContainText('OR CONTINUE IN THE SESSION');
    await expect(page.getByTestId('wf-terminal-command')).toHaveText(COMMAND);
    await expect(page.getByTestId('wf-terminal-lifetime')).toHaveText(
      `session lifetime ends ${ENDS_AT}`,
    );
  });

  test('never soft-wraps the command, because a wrapped command is a broken paste', async ({
    page,
  }) => {
    await open(page);

    const block = page.getByTestId('wf-terminal-command');
    await expect(block).toHaveCSS('white-space', 'pre');
    await expect(block).toHaveCSS('overflow-x', 'auto');
    // it really is wider than its own box, which is what makes the rule load-bearing here
    const overflows = await block.evaluate((el) => el.scrollWidth > el.clientWidth);
    expect(overflows).toBe(true);
  });

  test('is hidden for a Run the escape hatch does not apply to', async ({ page }) => {
    await open(page, detail({ run: { terminal: null } }));

    await expect(page.getByTestId('wf-terminal')).toHaveCount(0);
  });

  test('no secret value reaches the page: the credential is a shell reference', async ({
    page,
  }) => {
    await open(page);

    const rendered = await page.getByTestId('wf-terminal-command').textContent();
    expect(rendered).toContain('ANTHROPIC_AUTH_TOKEN="$LITELLM_API_KEY"');
    // the page expands nothing and adds nothing: what is on screen is what the server sent
    expect(rendered).toBe(COMMAND);
    expect(await page.content()).not.toContain('GITHUB_TOKEN');
  });
});

test.describe('Copy', () => {
  test('puts the command on the clipboard and posts terminal_start', async ({ page }) => {
    await open(page);
    const posted = collect(page, run({ terminal_session: true }));

    await page.getByTestId('wf-terminal-copy').click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({ kind: 'terminal_start' });
    const clipboard = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboard).toBe(COMMAND);
  });

  test('confirms COPIED in place for about 1.2 s, then reads COPY again', async ({ page }) => {
    await open(page);
    collect(page, run({ terminal_session: true }));
    const button = page.getByTestId('wf-terminal-copy');

    await button.click();

    await expect(button).toHaveText('COPIED');
    await expect(button).toHaveText('COPY', { timeout: 4000 });
  });
});

test.describe('while a session is in progress', () => {
  test('the line names every action it disables and how to get them back', async ({ page }) => {
    await open(page, inSessionDetail());

    await expect(page.getByTestId('wf-terminal-session')).toContainText(SESSION_LINE);
    await expect(page.getByTestId('wf-terminal-session')).toContainText(
      'the run resumes by itself when the story file is done and the tree is clean',
    );
  });

  test('the other actions are gone and only Release and Cancel run are left', async ({ page }) => {
    await open(page, inSessionDetail());

    await expect(page.getByTestId('wf-terminal-release')).toBeVisible();
    await expect(page.getByTestId('wf-cancel')).toBeVisible();
    await expect(page.getByTestId('wf-answer')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-skip_story')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-skip_epic')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-retry')).toHaveCount(0);
  });

  test('Release posts terminal_release', async ({ page }) => {
    await open(page, inSessionDetail());
    const posted = collect(page, run());

    await page.getByTestId('wf-terminal-release').click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({ kind: 'terminal_release' });
  });

  test('the actions come back once the server says the session ended', async ({ page }) => {
    await open(page, inSessionDetail());
    await expect(page.getByTestId('wf-terminal-release')).toBeVisible();
    collect(page, run());
    await mockDetail(page, detail());

    await page.getByTestId('wf-terminal-release').click();

    await expect(page.getByTestId('wf-terminal-release')).toHaveCount(0);
    await expect(page.getByTestId('wf-answer')).toBeVisible();
  });
});
