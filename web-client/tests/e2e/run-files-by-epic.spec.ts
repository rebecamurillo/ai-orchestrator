import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * Files by epic and story (epic 2 story 1, EXPERIENCE § 6.1): the panel's heading, the
 * `changed: 2 files` list, a path's inline diff, and the diagram's Files button highlighting
 * the story's row. Written, not run by the story that adds it.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad93a01';
const PAGE_URL = `/workflows/${RUN_ID}`;
const FOLDER = 'specs/epic-1-models';

async function mockRun(page: Page): Promise<void> {
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
    await page.getByTestId('wf-diagram-files-epics.0.stories.0').first().click();
    await expect(page.locator('#files-story-0-1')).toHaveClass(/wf-files-focus/);
  });
});
