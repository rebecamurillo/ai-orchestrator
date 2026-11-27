import { expect, test, type Page, type Route } from '@playwright/test';

import { twoEpicGraph, twoEpicSteps } from '../fixtures/run-graph';
import { runDetail, RUN_ID } from '../fixtures/run-detail';

/**
 * Files by epic and story (epic 2 story 1, EXPERIENCE § 6.1): the panel's heading, the
 * `changed: 2 files` list, a path's inline diff, and the diagram's Files button highlighting
 * the story's row. The Run's detail and graph are the shared fixtures `run-diagram.spec.ts`
 * reads: the shared stub knows no Run.
 */

const PAGE_URL = `/workflows/${RUN_ID}`;
const FOLDER = 'specs/epic-1-models';

async function mockRun(page: Page): Promise<void> {
  // `**` admits the `?opened=true` of the first fetch (story 8-3)
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(runDetail(twoEpicSteps())),
    }),
  );
  await page.route(`**/api/runs/${RUN_ID}/graph`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(twoEpicGraph()),
    }),
  );
  await page.route(`**/api/runs/${RUN_ID}/files-by-epic`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        epics: [
          {
            index: 0,
            title: 'models',
            folder: FOLDER,
            files: [`${FOLDER}/SPEC.md`, `${FOLDER}/stories.yaml`],
            stories: [
              {
                id: '1',
                title: 'model list',
                started: true,
                story_file: `${FOLDER}/stories/1-model-list.md`,
                changed: ['src/models.py', 'tests/test_models.py'],
              },
            ],
          },
          {
            index: 1,
            title: 'views',
            folder: 'specs/epic-2-views',
            files: [],
            stories: [
              {
                id: '1',
                title: 'view list',
                started: true,
                story_file: 'specs/epic-2-views/stories/1-view-list.md',
                changed: [],
              },
            ],
          },
        ],
      }),
    }),
  );
  await page.route(`**/api/runs/${RUN_ID}/files-by-epic/diff**`, (route: Route) => {
    const path = new URL(route.request().url()).searchParams.get('path') ?? '';
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        path,
        from_sha: 'aaa1111',
        to_sha: 'bbb2222',
        diff: `--- a/${path}\n+++ b/${path}\n-old\n+new\n`,
      }),
    });
  });
}

test.describe('files by epic and story', () => {
  test('lists changed paths and shows a path’s diff inline', async ({ page }) => {
    await mockRun(page);
    await page.goto(PAGE_URL);
    await expect(page.getByText('FILES · BY EPIC AND STORY')).toBeVisible();
    await expect(page.getByText('epic 1 · models')).toBeVisible();

    await page.getByText('changed: 2 files').click();
    await page.getByText('src/models.py', { exact: true }).click();
    await expect(page.locator('pre.wf-files-diff .wf-files-diff-add')).toContainText('+new');
    await expect(page.locator('pre.wf-files-diff .wf-files-diff-del')).toContainText('-old');
  });

  test('the diagram Files button highlights the story row', async ({ page }) => {
    await mockRun(page);
    await page.goto(PAGE_URL);
    // the running epic is the one the diagram opens; a collapsed epic draws no story card
    await page.getByTestId('wf-diagram-files-epics.1.stories.0').first().click();
    await expect(page.locator('#files-story-1-1')).toHaveClass(/wf-files-focus/);
  });
});
