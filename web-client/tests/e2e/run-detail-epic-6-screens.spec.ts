import { fileURLToPath, URL as NodeUrl } from 'node:url';

import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * Epic 6's own screenshot deliverable: one PNG per new human-gate state the epic added to
 * the Run detail screen (6.1 Answer, 6.2 checkpoints, 6.3 Artifacts, 6.4 Skip story, 6.5 Skip
 * epic, 6.6 Raise budget / Accept, 6.7 the terminal resume block), captured while this spec
 * runs under `make e2e-ui` — the same deliverable `run-detail-story-additions.spec.ts`'s own
 * module doc describes for Epic 5, and the same mechanism: `GET /runs/{id}/detail` (and, for
 * the states that read a second endpoint, `GET`/`PUT /runs/{id}/files`) mocked with
 * `page.route()`. There is no engine here — every state below is about rendering a given
 * response, not producing one — so each fixture below is lifted from the six specs Epic 6
 * already added (`run-detail-answer.spec.ts`, `-artifacts.spec.ts`, `-skip-story.spec.ts`,
 * `-skip-epic.spec.ts`, `-accept.spec.ts`, `-terminal.spec.ts`) rather than invented here.
 *
 * New file, for the reason every one of those gives: `run-detail.spec.ts` and
 * `run-detail-story-additions.spec.ts` are frozen and predate every control this epic adds.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939ee';
// Named `PAGE_URL`, not `URL` — `mockFiles` below needs the global `URL` constructor to
// parse a request's query string, the same reason `run-detail-artifacts.spec.ts` does.
const PAGE_URL = `/workflows/${RUN_ID}`;
// Resolved off this file's own URL, not `process.cwd()` — `page.screenshot({ path })` resolves
// a relative path against the runner's cwd, which is `web-client/` under `make e2e-ui` but not
// guaranteed to stay that way, and the repo-root screens directory is the actual deliverable.
const SCREENS = fileURLToPath(
  new NodeUrl('../../../_bmad-output/implementation-artifacts/epic-6-screens', import.meta.url),
);

// A real desktop layout, not a collapsed mobile column.
test.use({ viewport: { width: 1440, height: 900 } });

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'needs_you',
    admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'],
    branch: 'epics/1',
    budget_usd: '40.00',
    compare_urls: [],
    created_at: '2026-09-09T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: 'abc1234',
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '12.30',
    template: 'epic',
    terminal_session: false,
    version: 1,
    worktree_path: '/work/orchestrator',
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
        started_at: '2026-09-09T09:00:05Z',
        worktree_path: '/work/orchestrator',
      },
    },
    alert: null,
    steps: [],
    stories: [],
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
  // operator revision 2026-09-18: story 8-3 put `?opened=true` on the first detail fetch; the
  // trailing `**` admits the query string a bare glob never matches. `run-detail-last-opened.
  // spec.ts` AC1/AC3 assert the new behaviour.
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

const DEFAULT_TREE = {
  root: 'specs/gates',
  entries: [
    { path: 'specs/gates/SPEC.md', kind: 'file', size: 40, mtime: 0 },
    { path: 'specs/gates/stories.yaml', kind: 'file', size: 12, mtime: 0 },
  ],
};

/** The ARTIFACTS column's own tree fetch (mounted regardless of the stop shown) plus, for the
 * screens that need one, a specific file's content or the planned-story-file glob a spec
 * checkpoint reads (`run-detail-artifacts.spec.ts`'s own `mockFiles`, generalised so every
 * screen below gets a populated tree rather than the "could not read" error state). */
async function mockFiles(
  page: Page,
  files: Record<string, string> = {},
  tree: Record<string, unknown> = DEFAULT_TREE,
): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/files*`, (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.searchParams.get('path');

    if (request.method() === 'PUT') {
      const body = request.postDataJSON() as { path: string; content: string };
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          path: body.path,
          kind: 'file',
          size: body.content.length,
          mtime: 1,
        }),
      });
    }
    if (path && path in files) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ path, content: files[path], size: files[path].length, mtime: 0 }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(tree),
    });
  });
}

async function open(page: Page, body: Record<string, unknown>): Promise<void> {
  await mockDetail(page, body);
  await page.goto(PAGE_URL);
  await expect(page.getByTestId('wf-header')).toBeVisible();
}

test.describe('Epic 6 screens', () => {
  test('01 — blocked, with the Answer box filled in', async ({ page }) => {
    // The exact shape `run-detail-answer.spec.ts`'s own `detail()` fixture uses.
    await mockFiles(page);
    await open(
      page,
      detail({
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
            path: 'epics[0].stories[0].build',
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
        stories: [{ epic_index: 1, story_id: '4-1', state: 'current', cost_usd: '3.20' }],
        admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'],
        run: { admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'] },
      }),
    );

    await expect(page.getByTestId('wf-answer-hint')).toBeVisible();
    await page.getByTestId('wf-answer').fill("Post to the project's channel only");
    await expect(page.getByTestId('wf-signal-answer')).toBeEnabled();

    await page.screenshot({
      path: `${SCREENS}/01-run-detail-blocked-answer.png`,
      fullPage: true,
    });
  });

  test('02 — spec checkpoint, with the planned file and Reject revealed', async ({ page }) => {
    // The exact shape `run-stop-body-checkpoint.test.ts`'s own `specCheckpoint()` fixture uses.
    const plannedPath = 'specs/gates/stories/2-*.md';
    await mockFiles(page, {
      [plannedPath]:
        '# Story 2 — Record the plan\n\n- read the archive\n- write the plan\n\n' +
        'A plain paragraph describing the approach.',
    });
    await open(
      page,
      detail({
        alert: {
          token: 'CHK',
          reason: 'spec checkpoint',
          park_kind: 'checkpoint',
          row_kind: 'agent',
          attribution: {
            harness: 'claude',
            model: 'claude-opus-4',
            ended_at: '2026-09-09T09:05:00Z',
          },
        },
        steps: [
          {
            seq: 1,
            path: 'stories[0].build',
            label: 'build',
            kind: 'agent',
            gate: 'liveness',
            status: 'checkpoint',
            token: 'CHK',
            reason: null,
            attempts: 1,
            latest: null,
          },
        ],
        stories: [{ epic_index: 1, story_id: '2', state: 'current', cost_usd: '0.01' }],
        admitted_signals: ['answer', 'continue', 'skip_story', 'skip_epic', 'cancel'],
        run: { admitted_signals: ['answer', 'continue', 'skip_story', 'skip_epic', 'cancel'] },
      }),
    );

    await expect(page.getByTestId('wf-planned-file')).toBeVisible();
    await expect(page.getByTestId('wf-planned-file-eyebrow')).toBeVisible();
    await expect(page.getByTestId('wf-signal-continue')).toBeVisible();
    await page.getByTestId('wf-reject-open').click();
    await expect(page.getByTestId('wf-reject')).toBeVisible();
    await expect(page.getByTestId('wf-reject-hint')).toBeVisible();

    await page.screenshot({
      path: `${SCREENS}/02-run-detail-spec-checkpoint.png`,
      fullPage: true,
    });
  });

  test('03 — done checkpoint, with the summary line and Continue', async ({ page }) => {
    // The exact shape `run-stop-body-checkpoint.test.ts`'s own `doneCheckpoint()` fixture uses.
    await mockFiles(page);
    await open(
      page,
      detail({
        alert: {
          token: 'CHK',
          reason: 'story checkpoint',
          park_kind: 'checkpoint',
          row_kind: 'checkpoint',
          checkpoint_story: {
            story_id: '2',
            title: 'Record the plan',
            attempts: 1,
            cost_usd: '0.01',
            verify: 'done',
          },
        },
        stories: [{ epic_index: 1, story_id: '2', state: 'done', cost_usd: '0.01' }],
        admitted_signals: ['continue', 'skip_story', 'skip_epic', 'cancel'],
        run: { admitted_signals: ['continue', 'skip_story', 'skip_epic', 'cancel'] },
      }),
    );

    await expect(page.getByTestId('wf-checkpoint-summary')).toBeVisible();
    await expect(page.getByTestId('wf-signal-continue')).toBeVisible();

    await page.screenshot({
      path: `${SCREENS}/03-run-detail-done-checkpoint.png`,
      fullPage: true,
    });
  });

  test('04 — the ARTIFACTS panel, a Markdown file open in the editor', async ({ page }) => {
    // The exact shape `run-detail-artifacts.spec.ts`'s own fixtures use.
    const SPEC_FILE = 'specs/gates/SPEC.md';
    const STORIES_FILE = 'specs/gates/stories.yaml';
    const SPEC_CONTENT = '# Gates spec\n\nsome existing text.\n';
    await mockFiles(
      page,
      { [SPEC_FILE]: SPEC_CONTENT, [STORIES_FILE]: 'stories: []\n' },
      {
        root: 'specs/gates',
        entries: [
          { path: SPEC_FILE, kind: 'file', size: SPEC_CONTENT.length, mtime: 0 },
          { path: STORIES_FILE, kind: 'file', size: 12, mtime: 0 },
        ],
      },
    );
    await open(
      page,
      detail({
        alert: {
          token: 'BLK',
          reason: '## Auto Run Result\n\nWhich channel should the notification post to?',
          park_kind: 'blocked',
          attribution: null,
        },
        run: { branch: 'epics/gates' },
      }),
    );
    await expect(page.getByTestId('artifacts-tree')).toBeVisible();

    await page.getByTestId(`artifacts-file-${SPEC_FILE}`).click();
    await expect(page.getByTestId('wf-file-viewer')).toBeVisible();
    await page.getByTestId('wf-artifacts-edit').click();

    await expect(page.getByTestId('wf-editor')).toBeVisible();
    await expect(page.getByTestId('wf-editor-hint')).toBeVisible();
    await expect(page.getByTestId('wf-editor-save')).toBeVisible();

    await page.screenshot({
      path: `${SCREENS}/04-run-detail-artifacts-editor.png`,
      fullPage: true,
    });
  });

  test('05 — Skip story, its inline confirm on a verify_failed stop', async ({ page }) => {
    // The exact shape `run-detail-skip-story.spec.ts`'s own `detail()` fixture uses.
    await mockFiles(page);
    await open(
      page,
      detail({
        header: {
          meta: {
            project: 'Mixed Signals',
            repository: 'orchestrator',
            base_branch: 'main',
            folder: 'specs/gates',
            template: 'epic',
            version: 1,
            harness: 'fake',
            started_at: '2026-09-07T09:00:05Z',
            worktree_path: '/work/orchestrator',
          },
        },
        alert: {
          token: 'BLK',
          reason: 'verify failed 2/2',
          park_kind: 'verify_failed',
          row_kind: 'shell',
        },
        steps: [
          {
            seq: 1,
            path: 'epics[0].stories[2].verify',
            label: 'verify',
            kind: 'shell',
            gate: 'deterministic',
            status: 'error',
            token: 'ERR',
            reason: 'exit 1',
            attempts: 2,
            latest: null,
          },
        ],
        stories: [{ epic_index: 1, story_id: '4-3', state: 'current', cost_usd: '3.20' }],
        admitted_signals: ['retry', 'skip_story', 'skip_epic', 'cancel'],
        run: { admitted_signals: ['retry', 'skip_story', 'skip_epic', 'cancel'] },
      }),
    );

    await page.getByTestId('wf-signal-skip_story').click();
    await expect(page.getByTestId('wf-confirm-skip_story-line')).toBeVisible();
    await expect(page.getByTestId('wf-confirm-skip_story-yes')).toBeVisible();
    await expect(page.getByTestId('wf-confirm-skip_story-keep')).toBeVisible();

    await page.screenshot({
      path: `${SCREENS}/05-run-detail-skip-story-confirm.png`,
      fullPage: true,
    });
  });

  test('06 — Skip epic, its own inline confirm on a push_rejected stop', async ({ page }) => {
    // The exact shape `run-detail-skip-epic.spec.ts`'s own `detail()` fixture uses.
    await mockFiles(page);
    await open(
      page,
      detail({
        header: {
          meta: {
            project: 'Mixed Signals',
            repository: 'orchestrator',
            base_branch: 'main',
            folder: 'specs/gates',
            template: 'initiative',
            version: 1,
            harness: 'fake',
            started_at: '2026-09-07T09:00:05Z',
            worktree_path: '/work/orchestrator',
          },
        },
        alert: {
          token: 'BLK',
          reason: 'the remote rejected it',
          park_kind: 'push_rejected',
          row_kind: 'git.push',
        },
        steps: [
          {
            seq: 1,
            path: 'epics[0].push',
            label: 'push',
            kind: 'git.push',
            gate: 'deterministic',
            status: 'error',
            token: 'ERR',
            reason: 'rejected',
            attempts: 1,
            latest: null,
          },
        ],
        gate_record: [
          {
            id: '33333333-3333-3333-3333-333333333333',
            at: '2026-09-07T09:10:00Z',
            path: 'epics[0].push',
            event: 'push_rejected',
            actor: 'machine',
            text: 'the remote rejected it',
            attempt_n: null,
          },
        ],
        admitted_signals: ['retry', 'skip_epic', 'cancel'],
        run: { admitted_signals: ['retry', 'skip_epic', 'cancel'], template: 'initiative' },
      }),
    );

    await page.getByTestId('wf-signal-skip_epic').click();
    await expect(page.getByTestId('wf-confirm-skip_epic-line')).toBeVisible();
    await expect(page.getByTestId('wf-confirm-skip_epic-yes')).toBeVisible();
    await expect(page.getByTestId('wf-confirm-skip_epic-keep')).toBeVisible();

    await page.screenshot({
      path: `${SCREENS}/06-run-detail-skip-epic-confirm.png`,
      fullPage: true,
    });
  });

  test('07 — the budget park, with the pre-filled raise field', async ({ page }) => {
    // The exact shape `run-detail-accept.spec.ts`'s own `detail()` fixture uses.
    await mockFiles(page);
    await open(
      page,
      detail({
        alert: {
          token: 'BLK',
          reason: 'budget $41.20 / $40.00',
          park_kind: 'budget',
          row_kind: 'agent',
          payload: {},
        },
        steps: [
          {
            seq: 1,
            path: 'epics[0].stories[0].build',
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
        stories: [{ epic_index: 0, story_id: '4-1', state: 'current', cost_usd: '41.20' }],
        cost: {
          spent_usd: '41.20',
          budget_usd: '40.00',
          tokens_in: 15000,
          tokens_out: 4200,
          wall_clock_seconds: 930,
          active_seconds: 0,
          provisional: false,
          trace_url: null,
        },
        admitted_signals: ['budget_raise', 'cancel'],
        run: { admitted_signals: ['budget_raise', 'cancel'], spend_usd: '41.20' },
      }),
    );

    await expect(page.getByTestId('wf-stop-budget')).toBeVisible();
    await expect(page.getByTestId('wf-budget-raise-input')).toBeVisible();
    await expect(page.getByTestId('wf-budget-raise')).toBeVisible();

    await page.screenshot({
      path: `${SCREENS}/07-run-detail-budget-park.png`,
      fullPage: true,
    });
  });

  test('08 — the protected-path stop, with the file list and Accept changes', async ({ page }) => {
    // The exact shape `run-detail-accept.spec.ts`'s own `protectedPathDetail()` fixture uses.
    const TEST_FILE = 'tests/api/test_runs.py';
    const AGENTS = 'AGENTS.md';
    await mockFiles(page);
    await open(
      page,
      detail({
        alert: {
          token: 'BLK',
          reason: `protected path modified: ${TEST_FILE}, ${AGENTS}`,
          park_kind: 'protected_path',
          row_kind: 'agent',
          payload: {
            hits: [
              { path: TEST_FILE, kind: 'modified' },
              { path: AGENTS, kind: 'added' },
            ],
          },
        },
        steps: [
          {
            seq: 1,
            path: 'epics[0].stories[0].build',
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
        stories: [{ epic_index: 0, story_id: '4-1', state: 'current', cost_usd: '41.20' }],
        admitted_signals: ['continue', 'retry', 'skip_story', 'skip_epic', 'cancel'],
        run: { admitted_signals: ['continue', 'retry', 'skip_story', 'skip_epic', 'cancel'] },
      }),
    );

    await expect(page.getByTestId(`wf-accept-file-${TEST_FILE}`)).toBeVisible();
    await expect(page.getByTestId(`wf-accept-file-${AGENTS}`)).toBeVisible();
    await expect(page.getByTestId(`wf-accept-diff-${AGENTS}`)).toBeVisible();
    await expect(page.getByTestId('wf-accept-line')).toBeVisible();
    await expect(page.getByTestId('wf-accept')).toBeVisible();

    await page.screenshot({
      path: `${SCREENS}/08-run-detail-protected-path-accept.png`,
      fullPage: true,
    });
  });

  test('09 — the terminal resume command block', async ({ page }) => {
    // The exact shape `run-detail-terminal.spec.ts`'s own `detail()`/`COMMAND` fixture uses.
    const STORY_ID = '4-1';
    const SESSION = '1f0a0d3c-8b17-4a9e-9c2b-2d4e6f8a0b1c';
    const WORKTREE = '/work/acme/orchestrator/wt/epics-1';
    const ENDS_AT = '2026-10-07T09:00:00Z';
    const COMMAND =
      'docker compose exec -e ORCH_RUN_ID=01a06887 -e ORCH_ATTEMPT_ID=01a06888 ' +
      `-e ORCH_STORY_ID=${STORY_ID} -e ORCH_HARNESS=claude -e ORCH_PROJECT=acme ` +
      '-e ORCH_TAGS=run:01a06887,attempt:01a06888 ' +
      `-e ORCH_LANGFUSE_TAGS='["run:01a06887"]' -e TRACEPARENT=00-abc-def-01 ` +
      'backend-api sh -c \'export ANTHROPIC_AUTH_TOKEN="$LITELLM_API_KEY"; ' +
      `cd ${WORKTREE} && claude --resume ${SESSION}'`;

    await mockFiles(page);
    await open(
      page,
      detail({
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
            path: 'epics[0].stories[0].build',
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
        admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'],
        run: {
          admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'],
          spend_usd: '4.18',
          worktree_path: WORKTREE,
          terminal: { command: COMMAND, session_lifetime_ends_at: ENDS_AT, in_progress: false },
        },
      }),
    );

    await expect(page.getByTestId('wf-terminal')).toBeVisible();
    await expect(page.getByTestId('wf-terminal-command')).toHaveText(COMMAND);
    await expect(page.getByTestId('wf-terminal-copy')).toBeVisible();
    await expect(page.getByTestId('wf-terminal-lifetime')).toBeVisible();

    await page.screenshot({
      path: `${SCREENS}/09-run-detail-terminal-resume.png`,
      fullPage: true,
    });
  });

  test('10 — a terminal session in progress, with only Release and Cancel left', async ({
    page,
  }) => {
    // The exact shape `run-detail-terminal.spec.ts`'s own `inSessionDetail()` fixture uses.
    const STORY_ID = '4-1';
    const SESSION = '1f0a0d3c-8b17-4a9e-9c2b-2d4e6f8a0b1c';
    const WORKTREE = '/work/acme/orchestrator/wt/epics-1';
    const ENDS_AT = '2026-10-07T09:00:00Z';
    const COMMAND =
      'docker compose exec -e ORCH_RUN_ID=01a06887 -e ORCH_ATTEMPT_ID=01a06888 ' +
      `-e ORCH_STORY_ID=${STORY_ID} -e ORCH_HARNESS=claude -e ORCH_PROJECT=acme ` +
      '-e ORCH_TAGS=run:01a06887,attempt:01a06888 ' +
      `-e ORCH_LANGFUSE_TAGS='["run:01a06887"]' -e TRACEPARENT=00-abc-def-01 ` +
      'backend-api sh -c \'export ANTHROPIC_AUTH_TOKEN="$LITELLM_API_KEY"; ' +
      `cd ${WORKTREE} && claude --resume ${SESSION}'`;

    await mockFiles(page);
    await open(
      page,
      detail({
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
        stories: [{ epic_index: 0, story_id: STORY_ID, state: 'current', cost_usd: '4.18' }],
        admitted_signals: ['cancel', 'terminal_release'],
        run: {
          admitted_signals: ['cancel', 'terminal_release'],
          spend_usd: '4.18',
          worktree_path: WORKTREE,
          terminal_session: true,
          terminal: { command: COMMAND, session_lifetime_ends_at: ENDS_AT, in_progress: true },
        },
      }),
    );

    await expect(page.getByTestId('wf-terminal-session')).toBeVisible();
    await expect(page.getByTestId('wf-terminal-release')).toBeVisible();
    await expect(page.getByTestId('wf-cancel')).toBeVisible();
    await expect(page.getByTestId('wf-answer')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-skip_story')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-skip_epic')).toHaveCount(0);

    await page.screenshot({
      path: `${SCREENS}/10-run-detail-terminal-session.png`,
      fullPage: true,
    });
  });
});
