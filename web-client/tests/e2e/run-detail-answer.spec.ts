import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * The Answer box in a real browser (6.1, FR-18, UX-DR10, UX-DR17): typing enables the button,
 * clicking posts `{kind: answer, payload: {text}}` and re-fetches, and a 409 prints beside the
 * button with the box still holding what was typed.
 *
 * New file, the way `run-detail-story-additions.spec.ts`'s own module doc explains: the two
 * specs before it are frozen and predate this control entirely. `GET /api/runs/{id}/detail`
 * and `POST /api/runs/{id}/signals` are mocked with `page.route()` — there is no engine here
 * to block a real Story, and every AC below is about what the screen does with a given
 * response.
 *
 * What is *not* here is the markup and the copy: `tests/unit/run-stop-body-answer.test.ts`
 * asserts the verbatim hint, the test ids and the two stops that offer no box at all, where
 * they can be asserted without a browser.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939cc';
const URL = `/workflows/${RUN_ID}`;

const STORY_ID = '4-1';
const BUILD = 'epics[0].stories[0].build';
const ANSWER = "Post to the project's channel only";

const HINT =
  'Blocked story file archived to stories/.answers/4-1-attempt-1.md with your answer; ' +
  'story 4-1 re-planned with the answer as context. ' +
  'If the gap is in SPEC.md, edit SPEC.md on the branch instead.';

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
    spend_usd: '12.30',
    template: 'epic',
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
        folder: 'specs/gates',
        template: 'epic',
        version: 1,
        harness: 'claude',
        started_at: '2026-09-07T09:00:05Z',
        worktree_path: '/work/orchestrator',
      },
    },
    alert: {
      token: 'BLK',
      reason: '## Auto Run Result\n\nWhich channel should the notification post to?',
      park_kind: 'blocked',
      attribution: {
        harness: 'claude',
        model: 'claude-opus-4',
        ended_at: '2026-09-07T09:12:00Z',
      },
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
        reason: null,
        attempts: 1,
        latest: {
          n: 1,
          started_at: '2026-09-07T09:10:00Z',
          ended_at: '2026-09-07T09:12:00Z',
          seconds: 120,
          harness: 'claude',
          model: 'claude-opus-4',
          exit_code: 0,
          cost_usd: '3.20',
          log_tail: [],
        },
      },
    ],
    stories: [{ epic_index: 1, story_id: STORY_ID, state: 'current', cost_usd: '3.20' }],
    cost: {
      spent_usd: '12.30',
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

async function mockDetail(page: Page, body: Record<string, unknown>): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/detail`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

async function open(page: Page): Promise<void> {
  await mockDetail(page, detail());
  await page.goto(URL);
  await expect(page.getByTestId('wf-header')).toBeVisible();
}

test.describe('the Answer box', () => {
  test('is disabled until something is typed, and states what Resume will do', async ({ page }) => {
    await open(page);

    await expect(page.getByTestId('wf-answer-hint')).toHaveText(HINT);
    const button = page.getByTestId('wf-signal-answer');
    await expect(button).toBeDisabled();

    await page.getByTestId('wf-answer').fill('   ');
    await expect(button).toBeDisabled();

    await page.getByTestId('wf-answer').fill(ANSWER);
    await expect(button).toBeEnabled();
  });

  test('posts the answer with the operator’s text and re-fetches the detail', async ({ page }) => {
    await open(page);
    await page.getByTestId('wf-answer').fill(ANSWER);

    let posted: Record<string, unknown> | null = null;
    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) => {
      posted = route.request().postDataJSON() as Record<string, unknown>;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(run({ status: 'running' })),
      });
    });
    // what the next poll returns: FR-18's "the Run leaves `needs_you` as soon as
    // `signal_run` commits", so the stop body is gone by the time the re-fetch lands
    await mockDetail(page, detail({ run: { status: 'running' }, alert: null }));

    await page.getByTestId('wf-signal-answer').click();

    await expect.poll(() => posted).not.toBeNull();
    expect(posted!.kind).toBe('answer');
    expect(posted!.payload).toEqual({ text: ANSWER });
    await expect(page.getByTestId('wf-stop-blocked')).toHaveCount(0);
    await expect(page.getByTestId('wf-answer')).toHaveCount(0);
  });

  test('prints a refusal beside the button and keeps what was typed', async ({ page }) => {
    await open(page);
    await page.getByTestId('wf-answer').fill(ANSWER);

    await page.route(`**/api/runs/${RUN_ID}/signals`, (route: Route) =>
      route.fulfill({
        status: 409,
        contentType: 'application/problem+json',
        body: JSON.stringify({
          type: 'about:blank',
          title: 'conflict',
          status: 409,
          detail: 'signal answer invalid for status running / park None',
        }),
      }),
    );

    await page.getByTestId('wf-signal-answer').click();

    await expect(page.getByTestId('wf-answer-error')).toHaveText(
      'signal answer invalid for status running / park None',
    );
    await expect(page.getByTestId('wf-answer')).toHaveValue(ANSWER);
    await expect(page.getByTestId('wf-signal-answer')).toBeEnabled();
  });

  test('the skips and Cancel stay beside it', async ({ page }) => {
    await open(page);

    await expect(page.getByTestId('wf-signal-skip_story')).toBeVisible();
    await expect(page.getByTestId('wf-signal-skip_epic')).toBeVisible();
    await expect(page.getByTestId('wf-cancel')).toBeVisible();
  });
});
