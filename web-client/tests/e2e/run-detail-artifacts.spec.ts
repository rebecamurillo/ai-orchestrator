import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * The ARTIFACTS column in a real browser (6.3, FR-19, FR-23, UX-DR9, AC5): the tree renders,
 * opening a Markdown file shows it rendered with an Edit control, Edit turns it into the
 * textarea with the exact hint, *Save* posts the `PUT` and the tree's own mtime updates, and
 * a list file opens read-only with the planned line and no Edit control at all.
 *
 * `GET /api/runs/{id}/detail`, `GET /api/runs/{id}/files` (tree and one-file reads) and
 * `PUT /api/runs/{id}/files` are mocked with `page.route()`, the same way `run-detail-
 * answer.spec.ts` mocks the signal endpoints: there is no engine here to write a real
 * worktree, and the ACs are about what the screen does with a given response.
 *
 * What is *not* here is the markup shape and the pure derivations: `tests/unit/components/
 * run-artifacts.test.ts` and `tests/unit/lib/run-artifacts.test.ts` assert those without a
 * browser.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939dd';
const PAGE_URL = `/workflows/${RUN_ID}`;

const SPEC_FOLDER = 'specs/gates';
const SPEC_FILE = `${SPEC_FOLDER}/SPEC.md`;
const STORIES_FILE = `${SPEC_FOLDER}/stories.yaml`;
const BRANCH = 'epics/gates';
const SPEC_CONTENT = '# Gates spec\n\nsome existing text.\n';
const NEW_CONTENT = '# Gates spec\n\nedited by the operator.\n';
const PLAN_REF = 'abc1234';

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'needs_you',
    admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'],
    branch: BRANCH,
    budget_usd: '40.00',
    compare_urls: [],
    created_at: '2026-09-09T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: PLAN_REF,
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '12.30',
    template: 'epic',
    terminal_session: false,
    version: 1,
    worktree_path: '/work/acme/widgets/wt/gates',
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
        folder: SPEC_FOLDER,
        template: 'epic',
        version: 1,
        harness: 'claude',
        started_at: '2026-09-09T09:00:05Z',
        worktree_path: '/work/acme/widgets/wt/gates',
      },
    },
    alert: {
      token: 'BLK',
      reason: '## Auto Run Result\n\nWhich channel should the notification post to?',
      park_kind: 'blocked',
      attribution: null,
    },
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

function tree(mtime: number): Record<string, unknown> {
  return {
    root: SPEC_FOLDER,
    entries: [
      { path: SPEC_FILE, kind: 'file', size: SPEC_CONTENT.length, mtime },
      { path: STORIES_FILE, kind: 'file', size: 12, mtime: 0 },
    ],
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

async function mockFiles(page: Page, treeMtime: number): Promise<void> {
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
          mtime: treeMtime + 1,
        }),
      });
    }
    if (path === SPEC_FILE) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          path: SPEC_FILE,
          content: SPEC_CONTENT,
          size: SPEC_CONTENT.length,
          mtime: treeMtime,
        }),
      });
    }
    if (path === STORIES_FILE) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          path: STORIES_FILE,
          content: 'stories: []\n',
          size: 12,
          mtime: 0,
        }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(tree(treeMtime)),
    });
  });
}

async function open(page: Page): Promise<void> {
  await mockDetail(page, detail());
  await mockFiles(page, 0);
  await page.goto(PAGE_URL);
  await expect(page.getByTestId('wf-header')).toBeVisible();
  await expect(page.getByTestId('artifacts-tree')).toBeVisible();
}

test.describe('the ARTIFACTS column', () => {
  test('lists the spec folder’s own tree', async ({ page }) => {
    await open(page);

    await expect(page.getByTestId(`artifacts-file-${SPEC_FILE}`)).toBeVisible();
    await expect(page.getByTestId(`artifacts-file-${STORIES_FILE}`)).toBeVisible();
  });

  test('opens a Markdown file rendered, with an Edit control', async ({ page }) => {
    await open(page);

    await page.getByTestId(`artifacts-file-${SPEC_FILE}`).click();

    await expect(page.getByTestId('wf-file-viewer')).toContainText('Gates spec');
    await expect(page.getByTestId('wf-artifacts-edit')).toBeVisible();
  });

  test('Edit turns the viewer into the textarea with the exact hint', async ({ page }) => {
    await open(page);
    await page.getByTestId(`artifacts-file-${SPEC_FILE}`).click();

    await page.getByTestId('wf-artifacts-edit').click();

    await expect(page.getByTestId('wf-editor')).toHaveValue(SPEC_CONTENT);
    await expect(page.getByTestId('wf-editor-hint')).toHaveText(
      `saved as commit "spec: operator edit (orchestrator)" on ${BRANCH}`,
    );
  });

  test('Save posts the PUT and the tree’s own mtime updates', async ({ page }) => {
    await open(page);
    await page.getByTestId(`artifacts-file-${SPEC_FILE}`).click();
    await page.getByTestId('wf-artifacts-edit').click();

    await page.getByTestId('wf-editor').fill(NEW_CONTENT);

    let putBody: { path: string; content: string } | null = null;
    await page.route(`**/api/runs/${RUN_ID}/files*`, async (route: Route) => {
      if (route.request().method() === 'PUT') {
        putBody = route.request().postDataJSON() as { path: string; content: string };
      }
      // defers to the `mockFiles` handler `open()` already registered, which actually
      // fulfills the request — `route.continue()` would send it to the real network instead
      await route.fallback();
    });

    await page.getByTestId('wf-editor-save').click();

    await expect.poll(() => putBody).not.toBeNull();
    expect(putBody!.path).toBe(SPEC_FILE);
    expect(putBody!.content).toBe(NEW_CONTENT);
    await expect(page.getByTestId('wf-editor')).toHaveCount(0);
    await expect(page.getByTestId('wf-file-viewer')).toBeVisible();
  });

  test('stories.yaml opens read-only with the planned line, no Edit control', async ({ page }) => {
    await open(page);

    await page.getByTestId(`artifacts-file-${STORIES_FILE}`).click();

    await expect(page.getByTestId('artifacts-readonly')).toHaveText(
      `planned at ${PLAN_REF} — start a new run to change the list`,
    );
    await expect(page.getByTestId('wf-artifacts-edit')).toHaveCount(0);
  });

  test('a slow response for an earlier selection never overwrites a newer one (the staleness guard)', async ({
    page,
  }) => {
    await open(page);
    await page.route(
      `**/api/runs/${RUN_ID}/files?path=${encodeURIComponent(SPEC_FILE)}`,
      async (route: Route) => {
        // the first click's own response, deliberately slow — it must land after the second
        // click's response and still not overwrite what the second click asked for
        await new Promise((resolve) => setTimeout(resolve, 300));
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            path: SPEC_FILE,
            content: SPEC_CONTENT,
            size: SPEC_CONTENT.length,
            mtime: 0,
          }),
        });
      },
    );

    // operator revision 2026-09-18: story 1-6 made a file row open an `ArtifactModal` over the
    // panel, whose backdrop covers the tree, so the second selection is made after closing the
    // first rather than straight over it. The guard is the same one and still this file's
    // subject — the earlier selection's slow response must not land on the later one — and it
    // now lives in the modal's own `[runId, path]` effect cleanup rather than in the panel.
    await page.getByTestId(`artifacts-file-${SPEC_FILE}`).click();
    await expect(page.getByTestId('wf-artifact-modal')).toBeVisible();
    await page.getByRole('button', { name: 'Close' }).click();
    await page.getByTestId(`artifacts-file-${STORIES_FILE}`).click();

    await expect(page.getByTestId('artifacts-readonly')).toHaveText(
      `planned at ${PLAN_REF} — start a new run to change the list`,
    );
    // holds after the slow SPEC.md response has had time to land
    await page.waitForTimeout(400);
    await expect(page.getByTestId('artifacts-readonly')).toHaveText(
      `planned at ${PLAN_REF} — start a new run to change the list`,
    );
    await expect(page.getByTestId('wf-artifacts-edit')).toHaveCount(0);
  });
});
