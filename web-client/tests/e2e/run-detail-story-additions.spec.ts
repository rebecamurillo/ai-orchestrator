import { fileURLToPath, URL as NodeUrl } from 'node:url';

import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * Run detail — story 5.10's own additions (SPEC CAP-10, FR-16, FR-23, FR-28): the `blocked`
 * Question block with agent attribution, the `misconfigured` body with no Answer box, the
 * Stories strip states, and the cost figures with `provisional` and the trace link.
 *
 * New file, the way `run-detail.spec.ts`'s own module doc explains: `GET /runs/{id}/detail`
 * is mocked with `page.route()` — there is no engine here to walk a real plan or block a
 * real Story, and every AC below is about rendering a given response, not producing one.
 * `web-client/tests/e2e/run-detail.spec.ts` is frozen and predates every `park_kind` this
 * story adds, so this lives beside it rather than inside it.
 *
 * Also this epic's own screenshot deliverable: `_bmad-output/implementation-artifacts/
 * epic-5-screens/` gets one PNG per state below, captured while this spec runs under
 * `make e2e-ui`.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939bb';
const URL = `/workflows/${RUN_ID}`;
// Resolved off this file's own URL, not `process.cwd()` — `page.screenshot({ path })` resolves
// a relative path against the runner's cwd, which is `web-client/` under `make e2e-ui` but not
// guaranteed to stay that way, and the repo-root screens directory is the actual deliverable.
const SCREENS = fileURLToPath(
  new NodeUrl('../../../_bmad-output/implementation-artifacts/epic-5-screens', import.meta.url),
);

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
    template: 'initiative',
    terminal_session: false,
    version: 1,
    worktree_path: null,
    worktrees: [],
    accepted_paths: [],
    ...overrides,
  };
}

const STORIES = [
  { epic_index: 1, story_id: '1-1', state: 'done', cost_usd: '4.10' },
  { epic_index: 1, story_id: '1-2', state: 'current', cost_usd: '3.20' },
  { epic_index: 1, story_id: '1-3', state: 'future', cost_usd: '0.00' },
  { epic_index: 1, story_id: '1-4', state: 'skipped', cost_usd: '0.00' },
];

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
    stories: STORIES,
    cost: {
      spent_usd: '12.30',
      budget_usd: '40.00',
      tokens_in: 15000,
      tokens_out: 4200,
      wall_clock_seconds: 930,
      active_seconds: 0,
      provisional: true,
      trace_url: 'https://langfuse.example/trace/1',
    },
    gate_record: [],
    admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'],
    summary: null,
    ...overrides,
    run: run((overrides.run as Record<string, unknown>) ?? {}),
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

test.describe('/workflows/[id] — 5.10 additions', () => {
  test('a blocked story shows the whole question, attribution, admitted skips, the strip states, and provisional cost with a trace link', async ({
    page,
  }) => {
    await mockDetail(
      page,
      detail({
        alert: {
          token: 'BLK',
          reason:
            '## Auto Run Result\n\nWhich database migration tool should this story use?\n\n' +
            '- alembic\n- raw SQL\n\nEither is fine; alembic matches the rest of the codebase.',
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
            path: 'stories[0].build',
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
              log_tail: ['reading stories/1-2-*.md', 'status: blocked'],
              cost_provisional: true,
            },
            cost_usd: '3.20',
          },
        ],
        gate_record: [
          {
            id: 'g1',
            at: '2026-09-07T09:12:00Z',
            path: 'stories[0].build',
            event: 'blocked',
            actor: 'machine',
            text: '## Auto Run Result',
            attempt_n: 1,
          },
        ],
      }),
    );
    await page.goto(URL);
    await expect(page.getByTestId('wf-header')).toBeVisible();

    // the whole question, shown with its agent attribution eyebrow
    await expect(page.getByTestId('wf-question')).toContainText(
      'Which database migration tool should this story use?',
    );
    await expect(page.getByTestId('wf-question-eyebrow')).toContainText(
      'Agent · claude · claude-opus-4 · 2026-09-07T09:12:00Z',
    );

    // exactly the admitted signals a blocked stop renders, with the Answer box 6.1 adds
    await expect(page.getByTestId('wf-signal-skip_story')).toBeVisible();
    await expect(page.getByTestId('wf-signal-skip_epic')).toBeVisible();
    await expect(page.getByTestId('wf-cancel')).toBeVisible();
    await expect(page.getByTestId('wf-signal-answer')).toBeVisible();
    await expect(page.locator('textarea')).toHaveCount(1);

    // the Stories strip states
    await expect(page.getByTestId('wf-story-1-1')).toHaveAttribute('data-state', 'done');
    await expect(page.getByTestId('wf-story-1-2')).toHaveAttribute('data-state', 'current');
    await expect(page.getByTestId('wf-story-1-3')).toHaveAttribute('data-state', 'future');
    await expect(page.getByTestId('wf-story-1-4')).toHaveAttribute('data-state', 'skipped');

    // the cost figures, provisional, and the trace link
    await expect(page.getByTestId('wf-cost-provisional')).toBeVisible();
    await expect(page.getByTestId('wf-trace')).toHaveAttribute(
      'href',
      'https://langfuse.example/trace/1',
    );
    await expect(page.getByTestId('wf-trace')).toContainText('open in Langfuse');

    // The screenshot is taken before the tab is changed: what it is a screenshot *of* is the
    // blocked question, which is the default GATE panel.
    await page.screenshot({
      path: `${SCREENS}/01-run-detail-blocked-question.png`,
      fullPage: true,
    });

    // the step row's own cost cell reads provisional too
    // operator revision 2026-09-18: story 1-4 put the Steps table behind the STEPS tab; the
    // cell's own reading is unchanged. See `run-detail-tabs.spec.ts`.
    await page.getByRole('button', { name: 'STEPS' }).click();
    await expect(page.getByTestId('wf-step-1')).toContainText('$3.20 provisional');
  });

  test('a misconfigured park shows the condition, the file list, the log tail, and no Answer box', async ({
    page,
  }) => {
    await mockDetail(
      page,
      detail({
        alert: {
          token: 'BLK',
          reason: 'ambiguous story file: 1-2-a.md, 1-2-b.md',
          park_kind: 'misconfigured',
        },
        steps: [
          {
            seq: 1,
            path: 'stories[1].build',
            label: 'build',
            kind: 'agent',
            gate: 'liveness',
            status: 'error',
            token: 'ERR',
            reason: 'ambiguous story file: 1-2-a.md, 1-2-b.md',
            attempts: 1,
            latest: {
              n: 1,
              started_at: '2026-09-07T09:10:00Z',
              ended_at: '2026-09-07T09:11:00Z',
              seconds: 60,
              harness: 'claude',
              model: 'claude-opus-4',
              exit_code: 0,
              cost_usd: '0.40',
              log_tail: ['reading stories/1-2-*.md', 'two matches, refusing to guess'],
            },
          },
        ],
        gate_record: [
          {
            id: 'g1',
            at: '2026-09-07T09:11:00Z',
            path: 'stories[1].build',
            event: 'misconfigured',
            actor: 'machine',
            text: 'ambiguous story file: 1-2-a.md, 1-2-b.md',
            attempt_n: 1,
          },
        ],
        admitted_signals: ['retry', 'skip_story', 'skip_epic', 'cancel'],
      }),
    );
    await page.goto(URL);
    await expect(page.getByTestId('wf-header')).toBeVisible();

    await expect(page.getByTestId('wf-stop-misconfigured')).toContainText(
      'ambiguous story file: 1-2-a.md, 1-2-b.md',
    );
    await expect(page.getByTestId('wf-stop-files')).toContainText('1-2-a.md');
    await expect(page.getByTestId('wf-stop-files')).toContainText('1-2-b.md');
    await expect(page.getByTestId('wf-stop-misconfigured')).toContainText(
      'two matches, refusing to guess',
    );
    await expect(page.getByTestId('wf-signal-retry')).toBeVisible();
    await expect(page.locator('textarea')).toHaveCount(0);
    await expect(page.getByTestId('wf-question')).toHaveCount(0);

    await page.screenshot({
      path: `${SCREENS}/02-run-detail-misconfigured.png`,
      fullPage: true,
    });
  });
});
