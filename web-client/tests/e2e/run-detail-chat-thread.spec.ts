import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * The stop's chat thread on the Run page (story 3-3, AD-25): a failed thread's error shows
 * verbatim on the line right after the `wf-alert` aside. `GET /api/runs/{id}/detail` is mocked
 * with `page.route()`; the copy and markup are `tests/unit/run-chat-thread.test.ts`'s.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939d3';
const URL = `/workflows/${RUN_ID}`;
const BUILD = 'epics[0].stories[0].build';

function detail(chatThread: Record<string, unknown> | null): Record<string, unknown> {
  const admitted = ['answer', 'skip_story', 'skip_epic', 'cancel'];
  return {
    run: {
      id: RUN_ID,
      status: 'needs_you',
      admitted_signals: admitted,
      branch: 'epics/1',
      budget_usd: '40.00',
      compare_urls: [],
      created_at: '2026-11-02T09:00:00Z',
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
      park_seq: 3,
    },
    header: {
      meta: {
        project: 'Mixed Signals',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'specs/gates',
        template: 'epic',
        version: 1,
        harness: 'claude',
        started_at: '2026-11-02T09:00:05Z',
        worktree_path: '/work/orchestrator',
      },
    },
    alert: {
      token: 'BLK',
      reason: 'Which schema should the export use?',
      park_kind: 'blocked',
      attribution: { harness: 'claude', model: 'claude-opus-4', ended_at: '2026-11-02T09:12:00Z' },
      chat_thread: chatThread,
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
        latest: null,
      },
    ],
    stories: [{ epic_index: 1, story_id: '4-1', state: 'current', cost_usd: '3.20' }],
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
    admitted_signals: admitted,
    reply_available: false,
    resume_unavailable_reason: null,
    summary: null,
  };
}

async function open(page: Page, body: Record<string, unknown>): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
  await page.goto(URL);
  await expect(page.getByTestId('wf-header')).toBeVisible();
}

function nextAfterAlert(page: Page): Promise<string | null> {
  return page
    .getByTestId('wf-alert')
    .evaluate((alert) => alert.nextElementSibling?.getAttribute('data-testid') ?? null);
}

test.describe('the stop chat thread', () => {
  test('a failed thread shows its error right after the alert', async ({ page }) => {
    await open(
      page,
      detail({ provider: 'mattermost', state: 'failed', error: '403 bot not in channel' }),
    );

    await expect(page.getByTestId('wf-chat-thread')).toHaveAttribute('data-state', 'failed');
    await expect(page.getByTestId('wf-chat-thread')).toContainText(
      'thread post failed; not retried',
    );
    await expect(page.getByTestId('wf-chat-thread-error')).toHaveText('403 bot not in channel');
    expect(await nextAfterAlert(page)).toBe('wf-chat-thread');
  });

  test('an open thread names its platform and shows no error', async ({ page }) => {
    await open(page, detail({ provider: 'slack', state: 'open', error: null }));

    await expect(page.getByTestId('wf-chat-thread')).toContainText('thread posted to slack');
    await expect(page.getByTestId('wf-chat-thread-error')).toHaveCount(0);
  });

  test('a stop with no thread shows no line', async ({ page }) => {
    await open(page, detail(null));

    await expect(page.getByTestId('wf-alert')).toBeVisible();
    await expect(page.getByTestId('wf-chat-thread')).toHaveCount(0);
  });
});
