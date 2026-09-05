import { expect, test, type Page } from '@playwright/test';

import { DEMO_NAME, UNKNOWN_NAME } from './templates-fixtures.mjs';

/**
 * The Templates screen (3.5). `shell.spec.ts` is frozen and already proves bare `/templates`'
 * empty state against the stub's unconditionally-empty list route (the story's Design
 * Notes); this file proves what only a real page, with a real CodeMirror editor, can show:
 * the versions list's caller fragment, Validate's error readout, Save's next-version
 * round trip, and the step/accent highlighting. "Every version of every Template" (the
 * cross-Template half of AC1) is proven instead at the component layer
 * (`tests/unit/templates-components.test.ts`) — see the story's Design Notes.
 */

const RED = 'rgb(224, 82, 82)';
const ACCENT = 'rgb(127, 212, 193)';

/** Chromium under Playwright follows the *host* platform's native contenteditable
 * select-all shortcut, which differs by OS — unlike a plain `<textarea>`, CodeMirror's
 * content is a `contenteditable` div with no keymap of its own binding either combination,
 * so the browser's own default decides which one fires. */
const SELECT_ALL = process.platform === 'darwin' ? 'Meta+A' : 'Control+A';

const INVALID_EDIT = [
  'name: demo',
  'version: 1',
  'description: two steps for the templates screen fixtures',
  'parallel: 2',
  'inputs:',
  '  project: { type: project, required: true }',
  'steps:',
  '  - id: checkout',
  '    uses: git.worktree',
  '    with: { base: "main", branch: "chore/demo" }',
  '    gate: deterministic',
  '',
  '  - id: build',
  '    run: "make test"',
].join('\n');

const VALID_EDIT = [
  'name: demo',
  'version: 1',
  'description: two steps for the templates screen fixtures, edited',
  'inputs:',
  '  project: { type: project, required: true }',
  'steps:',
  '  - id: checkout',
  '    uses: git.worktree',
  '    with: { base: "main", branch: "chore/demo" }',
  '    gate: deterministic',
  '',
  '  - id: build',
  '    run: "make test"',
  '    gate: liveness',
].join('\n');

async function replaceEditorContent(page: Page, text: string): Promise<void> {
  const content = page.locator('[data-testid="templates-editor"] .cm-content');
  await content.click();
  await page.keyboard.press(SELECT_ALL);
  await page.keyboard.press('Backspace');
  await page.keyboard.type(text, { delay: 1 });
}

test.describe('/templates/{name}/{version}', () => {
  test('renders the versions list with the caller, the YAML with line numbers, and the inputs table', async ({
    page,
  }) => {
    const response = await page.goto(`/templates/${DEMO_NAME}/1`);

    expect(response?.status()).toBe(200);

    const row = page.getByTestId('templates-version-demo-1');
    await expect(row).toContainText('demo v1');
    await expect(row).toContainText('pinned by 0 runs');
    await expect(row).toContainText('called by helper@1');
    await expect(row).toContainText('read-only');

    await expect(page.getByTestId('templates-editor')).toContainText('checkout');
    await expect(page.locator('.cm-gutters')).toBeVisible();
    await expect(page.locator('.cm-lineNumbers').getByText('1', { exact: true })).toBeVisible();

    const inputs = page.getByTestId('templates-inputs');
    await expect(inputs).toContainText('project');
    await expect(inputs).toContainText('yes');

    await expect(page.getByTestId('templates-diagram')).toContainText(
      'diagram arrives with the next story',
    );
    await expect(page.getByTestId('templates-readout')).toContainText('valid ·');
    // Review Triage Log, story 3.5, finding 8: the brief's exact banner line
    await expect(page.getByText('editing as v2')).toBeVisible();
  });

  test('Validate reports a reserved key and an ungated step, and leaves the text untouched', async ({
    page,
  }) => {
    await page.goto(`/templates/${DEMO_NAME}/1`);

    await replaceEditorContent(page, INVALID_EDIT);
    await page.getByTestId('templates-validate').click();

    await expect(page.getByTestId('templates-readout')).toHaveText('1 errors');
    await expect(page.getByTestId('templates-readout')).toHaveCSS('color', RED);
    await expect(page.getByTestId('templates-errors')).toContainText('parallel is reserved');
    await expect(page.getByTestId('templates-errors')).toContainText('unvalidated · steps.build');

    await expect(page.locator('[data-testid="templates-editor"] .cm-content')).toContainText(
      'parallel: 2',
    );
  });

  test('Save with invalid content reports the errors under the editor, keeps the text, and does not crash', async ({
    page,
  }) => {
    await page.goto(`/templates/${DEMO_NAME}/1`);

    await replaceEditorContent(page, INVALID_EDIT);
    await page.getByTestId('templates-save').click();

    await expect(page.getByTestId('templates-errors')).toContainText('parallel is reserved');
    await expect(page.getByTestId('templates-readout')).toHaveText('1 errors');
    await expect(page.locator('[data-testid="templates-editor"] .cm-content')).toContainText(
      'parallel: 2',
    );
    // still on the same version, page fully functional — never a 500-style crash
    expect(new URL(page.url()).pathname).toBe(`/templates/${DEMO_NAME}/1`);
    await expect(page.getByTestId('templates-save')).toBeVisible();
  });

  test('Save navigates to the next version, and the previous version survives unchanged', async ({
    page,
  }) => {
    await page.goto(`/templates/${DEMO_NAME}/1`);

    await replaceEditorContent(page, VALID_EDIT);
    await Promise.all([
      page.waitForURL(`**/templates/${DEMO_NAME}/2`),
      page.getByTestId('templates-save').click(),
    ]);

    await expect(page.getByTestId('templates-version-demo-1')).toBeVisible();
    await expect(page.getByTestId('templates-version-demo-2')).toBeVisible();
    await expect(page.locator('[data-testid="templates-editor"] .cm-content')).toContainText(
      'edited',
    );

    await page.goto(`/templates/${DEMO_NAME}/1`);
    await expect(page.locator('[data-testid="templates-editor"] .cm-content')).not.toContainText(
      'edited',
    );
  });

  test('highlights the step under the cursor, and colours a uses: value with the accent', async ({
    page,
  }) => {
    await page.goto(`/templates/${DEMO_NAME}/1`);

    const usesValue = page.getByText('git.worktree');
    await expect(usesValue).toHaveCSS('color', ACCENT);

    await expect(page.locator('.cm-yaml-step-active')).toHaveCount(0);
    await usesValue.click();
    await expect(page.locator('.cm-yaml-step-active').first()).toBeVisible();
  });

  test('an unknown Template renders a distinct unavailable readout, with no crash', async ({
    page,
  }) => {
    const response = await page.goto(`/templates/${UNKNOWN_NAME}/1`);

    expect(response?.status()).toBe(200);
    await expect(page.getByTestId('templates-version-unavailable')).toContainText(
      'TEMPLATE UNAVAILABLE',
    );
  });

  test('a malformed version segment renders the unavailable readout, with no crash (Review Triage Log, story 3.5, finding 14)', async ({
    page,
  }) => {
    const response = await page.goto(`/templates/${DEMO_NAME}/abc`);

    expect(response?.status()).toBe(200);
    await expect(page.getByTestId('templates-version-unavailable')).toContainText(
      'TEMPLATE UNAVAILABLE',
    );
  });
});
