import { expect, test, type Page, type Route } from '@playwright/test';

import { runDetail, RUN_ID, withSteps } from '../fixtures/run-detail';
import { twoEpicGraph, twoEpicSteps } from '../fixtures/run-graph';
import { agentDrawer, shellDrawer, type StepDrawerOut } from '../fixtures/step-drawer';
import type { components } from '../../src/api/schema';

type LogPageOut = components['schemas']['LogPageOut'];

/**
 * Epic 2 (Run page review) across its stories, in a browser: the drawer's sections and its
 * close path (CAP-2), the log in words for every state (CAP-4), *download raw* on the step page,
 * and `no file yet` in the files tree (CAP-1). Every read is a `page.route` mock.
 */
const BASE_URL = `/workflows/${RUN_ID}`;
const ATTEMPT_ID = 'att-2';

function logPage(overrides: Partial<LogPageOut> = {}): LogPageOut {
  return {
    eof: true,
    lines: [],
    next_cursor: 0,
    reason: null,
    removed_at: null,
    state: 'text',
    ...overrides,
  };
}

async function mockRun(
  page: Page,
  drawer: (seq: number, n: number) => StepDrawerOut,
  log: LogPageOut = logPage({ lines: ['> git fetch origin', 'fetched'] }),
): Promise<string[]> {
  const requested: string[] = [];
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({ json: runDetail(withSteps(twoEpicSteps())) }),
  );
  await page.route(`**/api/runs/${RUN_ID}/graph`, (route: Route) =>
    route.fulfill({ json: twoEpicGraph() }),
  );
  await page.route(`**/api/runs/${RUN_ID}/steps/*/attempts/*/drawer`, (route: Route) => {
    const match = new URL(route.request().url()).pathname.match(/steps\/(\d+)\/attempts\/(\d+)/);
    const [seq, n] = [Number(match![1]), Number(match![2])];
    requested.push(`${seq}/${n}`);
    return route.fulfill({ json: drawer(seq, n) });
  });
  await page.route(`**/api/runs/${RUN_ID}/attempts/*/log**`, (route: Route) =>
    route.fulfill({ json: log }),
  );
  return requested;
}

async function openFromRow(page: Page): Promise<void> {
  await page.goto(BASE_URL);
  await page.getByRole('button', { name: 'STEPS' }).click();
  await page.locator('button.wf-step-open').first().click();
  await expect(page.getByTestId('wf-step-drawer')).toBeVisible();
}

test.describe('step drawer sections (CAP-2)', () => {
  test('shows header, files read and files written of an agent step, and links the full page', async ({
    page,
  }) => {
    await mockRun(page, () => agentDrawer());
    await openFromRow(page);

    const drawer = page.getByTestId('wf-step-drawer');
    await expect(drawer.getByRole('heading', { name: 'build' })).toBeFocused();
    await expect(drawer.getByText('2 attempts · $1.25')).toBeVisible();
    await expect(drawer.getByText('FILES READ')).toBeVisible();
    await expect(drawer.getByText('src/b.ts', { exact: true })).toBeVisible();
    await expect(drawer.getByText('FILES WRITTEN')).toBeVisible();
    await expect(drawer.getByText('src/a.ts +3 −1')).toBeVisible();
    await expect(page.getByTestId('wf-step-drawer-full')).toHaveAttribute(
      'href',
      `${BASE_URL}/steps/epics.0.stories.0.build`,
    );
  });

  test('says files read are not recorded and refs updated for a deterministic step', async ({
    page,
  }) => {
    await mockRun(page, () =>
      shellDrawer({
        files_written: {
          state: 'refs',
          commit: null,
          files: [],
          refs: ['main aaa1111 → bbb2222'],
        },
      }),
    );
    await openFromRow(page);

    const drawer = page.getByTestId('wf-step-drawer');
    await expect(
      drawer.getByText(
        'deterministic step · files read are not recorded; the command is in the log',
      ),
    ).toBeVisible();
    await expect(drawer.getByText('no file · refs updated: main aaa1111 → bbb2222')).toBeVisible();
    await expect(drawer.getByText('2m · exit 0')).toBeVisible();
  });

  test('shows the commit line before the files of a commit step', async ({ page }) => {
    await mockRun(page, () =>
      shellDrawer({
        files_written: {
          state: 'commit',
          commit: { sha: 'abcdef1234567', message: 'story 1: ship it (orchestrator)' },
          refs: [],
          files: [{ path: 'src/a.ts', added: null, removed: null }],
        },
      }),
    );
    await openFromRow(page);

    const drawer = page.getByTestId('wf-step-drawer');
    await expect(
      drawer.getByText('commit abcdef1 · story 1: ship it (orchestrator)'),
    ).toBeVisible();
    await expect(drawer.getByText('src/a.ts binary')).toBeVisible();
  });

  test('a run-order row reloads the drawer on its seq with n = 0', async ({ page }) => {
    const requested = await mockRun(page, (seq) => (seq === 14 ? shellDrawer() : agentDrawer()));
    await openFromRow(page);

    const order = page.getByTestId('wf-step-drawer-order');
    await expect(order.getByRole('button', { name: /build/ })).toHaveAttribute(
      'aria-current',
      'step',
    );
    await order.getByRole('button', { name: /verify/ }).click();

    await expect(
      page.getByTestId('wf-step-drawer').getByRole('heading', { name: 'verify' }),
    ).toBeVisible();
    expect(requested).toContain('14/0');
  });

  test('close returns focus to the row that opened the drawer', async ({ page }) => {
    await mockRun(page, () => agentDrawer());
    await openFromRow(page);

    await page.getByTestId('wf-step-drawer').getByRole('button', { name: 'close' }).click();

    await expect(page.getByTestId('wf-step-drawer')).toHaveCount(0);
    await expect(page.locator('button.wf-step-open').first()).toBeFocused();
    await expect(page.locator('tr.wf-step-selected')).toHaveCount(0);
  });
});

test.describe('logs in words (CAP-4)', () => {
  const finished = (): StepDrawerOut =>
    shellDrawer({
      header: {
        exit_code: 1,
        started_at: '2026-11-23T10:00:00Z',
        ended_at: '2026-11-23T10:00:42Z',
      },
      log: { attempt_id: ATTEMPT_ID, reason: null, removed_at: null, state: 'text' },
    });

  test('text: the lines and download raw', async ({ page }) => {
    await mockRun(page, finished);
    await openFromRow(page);

    const log = page.getByTestId('wf-step-drawer-log');
    await expect(log.getByText('LOG · ATTEMPT 1')).toBeVisible();
    await expect(log.getByText('> git fetch origin')).toBeVisible();
    await expect(log.getByRole('link', { name: 'download raw' })).toHaveAttribute(
      'href',
      `/api/v1/runs/${RUN_ID}/attempts/${ATTEMPT_ID}/log?download=true`,
    );
  });

  test('no output with no reason: the words line and download raw', async ({ page }) => {
    await mockRun(page, finished, logPage({ state: 'no_output' }));
    await openFromRow(page);

    const log = page.getByTestId('wf-step-drawer-log');
    await expect(log.getByText('no output · the command ran and printed nothing')).toBeVisible();
    await expect(log.getByRole('link', { name: 'download raw' })).toBeVisible();
  });

  test('no output with a reason: the reason and no download raw', async ({ page }) => {
    await mockRun(
      page,
      finished,
      logPage({ state: 'no_output', reason: 'no log was recorded for this attempt' }),
    );
    await openFromRow(page);

    const log = page.getByTestId('wf-step-drawer-log');
    await expect(log.getByText('no output · no log was recorded for this attempt')).toBeVisible();
    await expect(log.getByRole('link', { name: 'download raw' })).toHaveCount(0);
  });

  test('removed by the sweep: the date, exit and duration that were recorded', async ({ page }) => {
    await mockRun(
      page,
      finished,
      logPage({
        state: 'removed',
        removed_at: '2026-11-29T03:00:00Z',
        lines: ['log no longer on disk'],
      }),
    );
    await openFromRow(page);

    const log = page.getByTestId('wf-step-drawer-log');
    await expect(
      log.getByText(
        'log removed by the retention sweep on 2026-11-29 · exit 1 · 42s were recorded',
      ),
    ).toBeVisible();
    await expect(log.getByRole('link', { name: 'download raw' })).toHaveCount(0);
  });

  test('a skipped row: not run and its reason, with no log viewer', async ({ page }) => {
    await mockRun(page, () =>
      shellDrawer({
        attempts: [],
        header: {
          n: null,
          exit_code: null,
          started_at: null,
          ended_at: null,
          status: 'skipped',
          token: 'SKP',
        },
        log: {
          attempt_id: null,
          reason: 'skipped · no command',
          removed_at: null,
          state: 'not_run',
        },
      }),
    );
    await openFromRow(page);

    const log = page.getByTestId('wf-step-drawer-log');
    await expect(log.getByText('not run · skipped · no command')).toBeVisible();
    await expect(log.getByTestId('wf-log-lines')).toHaveCount(0);
  });

  test('the step page offers download raw when the log exists', async ({ page }) => {
    const attemptId = 'aaaaaaaa-0000-7000-a000-000000000001';
    await page.route(`**/api/runs/${RUN_ID}/steps/**`, (route: Route) =>
      route.fulfill({
        json: {
          seq: 1,
          path: 'stories[0].build',
          label: 'build',
          kind: 'agent',
          gate: 'liveness',
          status: 'done',
          token: 'DON',
          reason: null,
          with_resolved: {},
          attempts: [
            {
              id: attemptId,
              n: 1,
              status: 'done',
              token: 'DON',
              started_at: '2026-11-23T10:00:00Z',
              ended_at: '2026-11-23T10:00:45Z',
              seconds: 45,
              harness: 'local',
              model: 'claude-sonnet-4-6',
              session_id: null,
              exit_code: 0,
              cost_usd: '0.42',
              cost_provisional: false,
              tokens_in: 100,
              tokens_out: 50,
              dispatch_prompt: 'Build.',
              retry_prompt: null,
              result: 'Done.',
              command: null,
              resume_command: null,
            },
          ],
        },
      }),
    );
    await page.route(`**/api/runs/${RUN_ID}/attempts/*/log**`, (route: Route) =>
      route.fulfill({ json: logPage({ lines: ['built'] }) }),
    );
    await page.goto(`${BASE_URL}/steps/stories.0.build`);
    await expect(page.getByTestId('step-detail')).toBeVisible();

    await expect(page.getByText('built', { exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'download raw' })).toHaveAttribute(
      'href',
      `/api/v1/runs/${RUN_ID}/attempts/${attemptId}/log?download=true`,
    );
  });
});

test.describe('files by epic and story (CAP-1)', () => {
  test('a story not started reads no file yet', async ({ page }) => {
    const folder = 'specs/epic-1-models';
    await mockRun(page, () => agentDrawer());
    await page.route(`**/api/runs/${RUN_ID}/files-by-epic`, (route: Route) =>
      route.fulfill({
        json: {
          epics: [
            {
              index: 0,
              title: 'models',
              folder,
              files: [`${folder}/SPEC.md`],
              stories: [
                {
                  id: '1',
                  title: 'model list',
                  started: true,
                  story_file: `${folder}/stories/1-model-list.md`,
                  changed: [],
                },
                { id: '2', title: 'model form', started: false, story_file: null, changed: [] },
              ],
            },
          ],
        },
      }),
    );
    await page.goto(BASE_URL);

    const panel = page.getByTestId('wf-artifacts');
    await expect(panel.getByText('FILES · BY EPIC AND STORY')).toBeVisible();
    // the anchor holds the story's label; its file, `no file yet` and `changed:` are siblings
    const notStarted = panel.locator('#files-story-0-2').locator('xpath=..');
    const started = panel.locator('#files-story-0-1').locator('xpath=..');
    await expect(panel.locator('#files-story-0-2')).toHaveText('story 2 · model form');
    await expect(notStarted).toContainText('no file yet');
    await expect(started).not.toContainText('no file yet');
    await expect(started).not.toContainText('changed:');
    await expect(panel.getByText('no file yet')).toHaveCount(1);
  });
});
