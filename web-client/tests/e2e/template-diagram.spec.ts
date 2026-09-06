import { expect, test, type Page } from '@playwright/test';

import {
  DEMO_NAME,
  DIAGRAM_EDIT,
  DIAGRAM_EDIT_NODE_IDS,
  DIAGRAM_INVALID_EDIT,
  EPIC_NAME,
  EPIC_NODE_IDS,
} from './templates-fixtures.mjs';

/**
 * The Templates screen's third column (3.6): the diagram, drawn from the backend's graph and
 * kept level with the editor beside it.
 *
 * A real browser is the only place most of this can be asserted. The layout is dagre's, the
 * hand-off between the two islands is a nanostore, and "no signal colour" is a computed
 * style — none of which exists in `environment: 'node'`, where `vitest.config.ts` runs. What
 * the unit suite proves is the picture a given graph draws
 * (`tests/unit/diagram-island.test.ts`); what this file proves is that the page fetches a
 * real graph, redraws it when the text validates, and holds the last valid one when it does
 * not.
 */

const ACCENT = 'rgb(127, 212, 193)';
/** `--color-line` and `--color-line-strong`: the node border and the loop rectangle. */
const LINE = 'rgb(33, 39, 42)';
const LINE_STRONG = 'rgb(44, 52, 56)';
const SIGNAL = ['rgb(79, 180, 119)', 'rgb(228, 179, 60)', 'rgb(224, 82, 82)'];

/** Same reasoning as `templates.spec.ts`: CodeMirror's content is a `contenteditable` div
 * with no select-all keymap of its own, so the host platform's shortcut is what fires. */
const SELECT_ALL = process.platform === 'darwin' ? 'Meta+A' : 'Control+A';

async function replaceEditorContent(page: Page, text: string): Promise<void> {
  const content = page.locator('[data-testid="templates-editor"] .cm-content');
  await content.click();
  await page.keyboard.press(SELECT_ALL);
  await page.keyboard.press('Backspace');
  await page.keyboard.type(text, { delay: 1 });
}

/** Every `diagram-node-<id>` currently drawn, in document order. */
async function drawnNodeIds(page: Page): Promise<string[]> {
  const ids = await page
    .locator('[data-testid="templates-diagram"] [data-testid^="diagram-node-"]')
    .evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute('data-testid')!.replace('diagram-node-', '')),
    );
  return ids;
}

test.describe('/templates/{name}/{version} — the diagram', () => {
  test('draws the stored version as one box per step, with no stale line', async ({ page }) => {
    await page.goto(`/templates/${DEMO_NAME}/1`);

    const diagram = page.getByTestId('templates-diagram');
    await expect(diagram.locator('svg')).toHaveAttribute('role', 'img');
    await expect(diagram.locator('svg')).toHaveAttribute(
      'aria-label',
      `template ${DEMO_NAME} v1 · 2 steps`,
    );
    expect(await drawnNodeIds(page)).toEqual(['checkout', 'build']);
    await expect(page.getByTestId('templates-diagram-stale')).toHaveCount(0);
  });

  test('redraws with the new steps when the edited text validates', async ({ page }) => {
    await page.goto(`/templates/${DEMO_NAME}/1`);

    await replaceEditorContent(page, DIAGRAM_EDIT);
    await page.getByTestId('templates-validate').click();

    await expect(page.getByTestId('diagram-node-stories.story')).toBeVisible();
    expect(await drawnNodeIds(page)).toEqual(DIAGRAM_EDIT_NODE_IDS);
    await expect(page.getByTestId('templates-diagram-stale')).toHaveCount(0);
    await expect(page.getByTestId('templates-diagram').locator('svg')).toHaveAttribute(
      'aria-label',
      `template ${DEMO_NAME} v1 · 5 steps`,
    );
  });

  test('reads a collapsed call, an ungated step and a loop the way the file declares them', async ({
    page,
  }) => {
    await page.goto(`/templates/${DEMO_NAME}/1`);

    await replaceEditorContent(page, DIAGRAM_EDIT);
    await page.getByTestId('templates-validate').click();
    await expect(page.getByTestId('diagram-node-stories.story')).toBeVisible();

    // a call is one node: the callee it pinned, and no gate of its own
    await expect(page.getByTestId('diagram-node-stories.story')).toContainText('helper@1');
    await expect(page.getByTestId('diagram-node-stories.story')).toContainText('template');
    // a step the file gated with nothing says so, as a plain word (NFR-2)
    await expect(page.getByTestId('diagram-node-draft')).toContainText('unvalidated');
    // an item checkpoint is a person's decision, as a plain word
    await expect(page.getByTestId('diagram-node-stories.after')).toContainText('human');
    // the loop is one dashed box around exactly its members
    const group = page.getByTestId('diagram-group-stories');
    await expect(group).toBeVisible();
    await expect(group.locator('rect')).toHaveCSS('stroke', LINE_STRONG);
    await expect(group.locator('rect')).toHaveCSS('stroke-dasharray', '3px, 3px');
  });

  test('accents the step that dispatches a harness, and nothing else', async ({ page }) => {
    await page.goto(`/templates/${DEMO_NAME}/1`);

    await replaceEditorContent(page, DIAGRAM_EDIT);
    await page.getByTestId('templates-validate').click();
    await expect(page.getByTestId('diagram-node-build')).toBeVisible();

    await expect(page.getByTestId('diagram-node-build').locator('rect')).toHaveCSS(
      'stroke',
      ACCENT,
    );
    await expect(page.getByTestId('diagram-node-build')).toContainText('agent');
    await expect(page.getByTestId('diagram-node-checkout').locator('rect')).toHaveCSS(
      'stroke',
      LINE,
    );
  });

  test('carries no signal colour: a Template has no status to report', async ({ page }) => {
    await page.goto(`/templates/${DEMO_NAME}/1`);

    await replaceEditorContent(page, DIAGRAM_EDIT);
    await page.getByTestId('templates-validate').click();
    await expect(page.getByTestId('diagram-node-build')).toBeVisible();

    const painted = await page
      .locator(
        [
          '[data-testid="templates-diagram"] rect',
          '[data-testid="templates-diagram"] text',
          '[data-testid="templates-diagram"] polyline',
          '[data-testid="templates-diagram"] polygon',
          '[data-testid="templates-diagram"] line',
        ].join(', '),
      )
      .evaluateAll((elements) =>
        elements.flatMap((element) => {
          const style = getComputedStyle(element);
          return [style.stroke, style.fill, style.color];
        }),
      );

    for (const signal of SIGNAL) expect(painted).not.toContain(signal);
  });

  test('holds the last valid picture when the edited text stops validating', async ({ page }) => {
    await page.goto(`/templates/${DEMO_NAME}/1`);

    await replaceEditorContent(page, DIAGRAM_EDIT);
    await page.getByTestId('templates-validate').click();
    await expect(page.getByTestId('diagram-node-stories.story')).toBeVisible();

    await replaceEditorContent(page, DIAGRAM_INVALID_EDIT);
    await page.getByTestId('templates-validate').click();

    await expect(page.getByTestId('templates-readout')).toHaveText('1 errors');
    await expect(page.getByTestId('templates-diagram-stale')).toHaveText(
      'diagram from last valid version',
    );
    // above the picture, not under it: the caveat is read before the thing it qualifies
    expect(
      await page.evaluate(() => {
        const stale = document.querySelector('[data-testid="templates-diagram-stale"]')!;
        const picture = document.querySelector('[data-testid="templates-diagram"]')!;
        return stale.compareDocumentPosition(picture) & Node.DOCUMENT_POSITION_FOLLOWING;
      }),
    ).toBeTruthy();
    // the previous graph's ids, byte for byte — nothing from the text that failed
    expect(await drawnNodeIds(page)).toEqual(DIAGRAM_EDIT_NODE_IDS);
    await expect(page.getByTestId('diagram-node-nothing-like-the-last-one')).toHaveCount(0);
  });

  test('holds the last valid picture when the graph request itself does not answer one', async ({
    page,
  }) => {
    await page.goto(`/templates/${DEMO_NAME}/1`);
    await expect(page.getByTestId('diagram-node-checkout')).toBeVisible();
    const before = await drawnNodeIds(page);

    // the text validates; only the request for its graph fails. The picture must not change,
    // and must not go on claiming to be the text on screen.
    await page.route('**/api/templates/*/graph', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/problem+json',
        body: JSON.stringify({ title: 'internal server error', status: 500 }),
      }),
    );

    await replaceEditorContent(page, DIAGRAM_EDIT);
    await page.getByTestId('templates-validate').click();

    await expect(page.getByTestId('templates-readout')).toContainText('valid ·');
    await expect(page.getByTestId('templates-diagram-stale')).toHaveText(
      'diagram from last valid version',
    );
    expect(await drawnNodeIds(page)).toEqual(before);
  });

  test('holds the last valid picture when the Validate request itself fails', async ({ page }) => {
    await page.goto(`/templates/${DEMO_NAME}/1`);
    await expect(page.getByTestId('diagram-node-checkout')).toBeVisible();
    const before = await drawnNodeIds(page);

    await page.route('**/api/templates/*/validate', (route) => route.abort());

    await replaceEditorContent(page, DIAGRAM_EDIT);
    await page.getByTestId('templates-validate').click();

    await expect(page.getByTestId('templates-diagram-stale')).toHaveText(
      'diagram from last valid version',
    );
    expect(await drawnNodeIds(page)).toEqual(before);
  });
});

/**
 * The story's first acceptance criterion, at the surface it names: the shipped `epic@1`, in a
 * browser, on its own route. The stub answers the same `{nodes, edges, groups}` the real
 * backend does for that file (`backend-api/tests/e2e/test_template_graph.py` pins it there),
 * so what this proves is the drawing of it end to end rather than the shape.
 */
test.describe('/templates/epic/1 — the shipped epic, drawn', () => {
  test('draws every step, the collapsed call, the item checkpoint and the loop box', async ({
    page,
  }) => {
    await page.goto(`/templates/${EPIC_NAME}/1`);

    expect(await drawnNodeIds(page)).toEqual(EPIC_NODE_IDS);
    await expect(page.getByTestId('diagram-node-stories.story')).toContainText('story@1');
    await expect(page.getByTestId('diagram-node-stories.after')).toContainText('human');
    await expect(page.getByTestId('diagram-group-stories')).toBeVisible();
    await expect(page.getByTestId('templates-diagram').locator('svg')).toHaveAttribute(
      'aria-label',
      `template ${EPIC_NAME} v1 · 6 steps`,
    );
    await expect(page.getByTestId('templates-diagram-stale')).toHaveCount(0);
  });

  test('reads left to right, in the order the file declares', async ({ page }) => {
    await page.goto(`/templates/${EPIC_NAME}/1`);
    await expect(page.getByTestId('diagram-node-link')).toBeVisible();

    const lefts = await Promise.all(
      EPIC_NODE_IDS.map(async (id) => {
        const box = await page.getByTestId(`diagram-node-${id}`).boundingBox();
        return box!.x;
      }),
    );

    for (let i = 1; i < lefts.length; i++) {
      expect(lefts[i]!, EPIC_NODE_IDS[i]).toBeGreaterThan(lefts[i - 1]!);
    }
  });

  test('has no amber and no red pixel: nothing is running', async ({ page }) => {
    await page.goto(`/templates/${EPIC_NAME}/1`);
    await expect(page.getByTestId('diagram-node-link')).toBeVisible();

    const painted = await page
      .locator('[data-testid="templates-diagram"] *')
      .evaluateAll((elements) =>
        elements.flatMap((element) => {
          const style = getComputedStyle(element);
          return [style.stroke, style.fill, style.color, style.backgroundColor, style.borderColor];
        }),
      );

    for (const signal of SIGNAL) expect(painted).not.toContain(signal);
  });
});
