import { expect, test, type Page } from '@playwright/test';

import { CLEAN_ID, MIXED_ID, NO_REPOS_ID, UNKNOWN_ID } from './projects-fixtures.mjs';

/**
 * The Projects screen (2.4). `shell.spec.ts` is frozen and already proves the empty state at
 * bare `/projects` against the stub's unconditionally-empty list route; this file proves
 * what only a real page can show: that `?id=` selects the right detail via its own
 * `GET /api/v1/projects/{id}` call, that the failed row's *re-run check* does a real round
 * trip with no client JavaScript, and that a fully-`ok` Project paints no signal colour.
 * "Two rows render, one selected" is proven at the component layer instead
 * (`tests/unit/projects-components.test.ts`) — see the story's Design Notes.
 */

const AMBER = 'rgb(228, 179, 60)';
const RED = 'rgb(224, 82, 82)';

/** Copied from `shell.spec.ts`'s local helper — that file is frozen, so this is its own. */
async function paintedColours(
  page: Page,
): Promise<{ selector: string; property: string; value: string }[]> {
  return page.evaluate(() => {
    const found: { selector: string; property: string; value: string }[] = [];
    const describe = (element: Element): string => {
      const id = element.getAttribute('data-testid');
      return `${element.tagName.toLowerCase()}${id ? `[data-testid=${id}]` : ''}`;
    };

    const collect = (element: Element, pseudo: string | null) => {
      const style = getComputedStyle(element, pseudo);
      const selector = `${describe(element)}${pseudo ?? ''}`;
      const record = (property: string) => {
        const value = style.getPropertyValue(property);
        if (value) found.push({ selector, property, value });
      };

      record('color');
      record('background-color');
      record('background-image');
      record('box-shadow');
      for (const side of ['top', 'right', 'bottom', 'left']) {
        if (style.getPropertyValue(`border-${side}-width`) !== '0px') {
          record(`border-${side}-color`);
        }
      }
      if (style.getPropertyValue('outline-style') !== 'none') record('outline-color');
    };

    for (const element of document.querySelectorAll('*')) {
      collect(element, null);
      collect(element, '::before');
      collect(element, '::after');
    }
    return found;
  });
}

test.describe('bare /projects', () => {
  test('shows the empty state and the always-present + New project link', async ({ page }) => {
    const response = await page.goto('/projects');

    expect(response?.status()).toBe(200);
    await expect(page.getByTestId('projects-empty')).toContainText('NO PROJECTS');
    await expect(page.getByTestId('projects-new')).toHaveAttribute('href', '/projects/new');
    await expect(page.getByTestId('projects-edit')).toHaveCount(0);
  });
});

test.describe('?id=<MIXED>', () => {
  test('renders the detail pane in order, below the list pane', async ({ page }) => {
    await page.goto(`/projects?id=${MIXED_ID}`);

    const detail = page.getByTestId('projects-detail');
    await expect(detail).toBeVisible();
    await expect(detail).toContainText('Mixed Signals');
    await expect(detail).toContainText('mixed-signals');
    await expect(detail).toContainText('created 2026-01-05');
    await expect(detail).toContainText('log_prompt_content on');
    await expect(detail).toContainText(
      'written to project-context.md in the spec folder before every story',
    );
    await expect(detail).toContainText(
      'A BMAD workflow repository and the docs site that tracks it.',
    );
    await expect(detail).toContainText('no runs yet');

    // the `+ Edit` filter only ever appears once a Project is selected
    await expect(page.getByTestId('projects-edit')).toHaveAttribute(
      'href',
      `/projects/${MIXED_ID}/edit`,
    );

    // `GET /api/v1/projects` answers empty unconditionally (the design note this story's
    // Design Notes section explains): the list pane above the detail is the empty state, not
    // a populated row. "Two rows render, one selected" is proven instead at the component
    // layer, in `tests/unit/projects-components.test.ts`.
    const listBox = await page.getByTestId('projects-empty').boundingBox();
    const detailBox = await detail.boundingBox();
    expect(listBox!.y).toBeLessThan(detailBox!.y);

    // the AC's own claimed order: title, meta, CONTEXT, REPOSITORIES, SETTINGS, RUNS ON THIS
    // PROJECT, in that sequence — not merely present somewhere, as `toContainText` alone
    // would allow
    const text = await detail.innerText();
    let cursor = -1;
    for (const marker of [
      'Mixed Signals',
      'created 2026-01-05',
      'CONTEXT',
      'REPOSITORIES',
      'SETTINGS',
      'RUNS ON THIS PROJECT',
      'no runs yet',
    ]) {
      const index = text.indexOf(marker, cursor + 1);
      expect(index, `expected "${marker}" after position ${cursor} in:\n${text}`).toBeGreaterThan(
        cursor,
      );
      cursor = index;
    }
  });

  test('reads every clone-check and method cell state', async ({ page }) => {
    await page.goto(`/projects?id=${MIXED_ID}`);

    const ok = page.getByTestId('projects-repo-orchestrator-api');
    await expect(ok).toContainText('6.11.0');
    await expect(ok).toContainText('ok · 15s');

    const failed = page.getByTestId('projects-repo-orchestrator-web');
    await expect(failed).toContainText('failed · new runs blocked');
    await expect(failed.locator('[data-signal="failed"]')).toHaveCSS('color', RED);

    const missing = page.getByTestId('projects-repo-orchestrator-docs');
    await expect(missing).toContainText('missing');
    await expect(missing).toContainText('— none declared');
    await expect(missing).toContainText('verify step will be skipped');

    const pending = page.getByTestId('projects-repo-orchestrator-infra');
    await expect(pending).toContainText('pending · save to check');
    await expect(pending).toContainText('—');
  });

  test('shows the failed row output, hint, and recheck control', async ({ page }) => {
    await page.goto(`/projects?id=${MIXED_ID}`);

    await expect(page.getByText('fatal: could not read Username')).toBeVisible();
    await expect(page.getByText('add a deploy key or a GITHUB_TOKEN')).toBeVisible();
    await expect(page.getByTestId('projects-recheck-orchestrator-web')).toHaveText('re-run check');
  });

  test('re-running the check does a full round trip with no client JavaScript', async ({
    page,
  }) => {
    await page.goto(`/projects?id=${MIXED_ID}`);

    // `orchestrator-recheck` is a dedicated fixture, mutated by no other test in this file —
    // `orchestrator-web` stays `failed` throughout the suite regardless of run order
    const [response] = await Promise.all([
      page.waitForResponse((candidate) => candidate.request().method() === 'POST'),
      page.getByTestId('projects-recheck-orchestrator-recheck').click(),
    ]);

    expect(response.status()).toBe(200);
    expect(new URL(page.url()).searchParams.get('id')).toBe(MIXED_ID);
    await expect(page.getByTestId('projects-repo-orchestrator-recheck')).toContainText('ok · 3s');
    await expect(page.getByTestId('projects-repo-orchestrator-recheck')).not.toContainText(
      'failed · new runs blocked',
    );
  });

  test('re-running a check the backend refuses still renders the page, with no crash', async ({
    page,
  }) => {
    // the I/O matrix's "a backend refusal surfaces via ActionError, page still renders": the
    // stub's clone-check route only recognises `orchestrator-recheck`'s id, so submitting
    // `orchestrator-web`'s form 404s upstream without mutating anything
    await page.goto(`/projects?id=${MIXED_ID}`);

    const [response] = await Promise.all([
      page.waitForResponse((candidate) => candidate.request().method() === 'POST'),
      page.getByTestId('projects-recheck-orchestrator-web').click(),
    ]);

    expect(response.status()).toBeLessThan(500);
    await expect(page.getByTestId('projects-detail')).toBeVisible();
    await expect(page.getByTestId('projects-repo-orchestrator-web')).toContainText(
      'failed · new runs blocked',
    );
  });
});

test.describe('?id=<CLEAN>', () => {
  test('paints no amber or red pixel when every Repository is ok', async ({ page }) => {
    await page.goto(`/projects?id=${CLEAN_ID}`);

    await expect(page.getByTestId('projects-detail')).toBeVisible();
    const painted = await paintedColours(page);
    const signals = painted.filter(
      (entry) => entry.value.includes(AMBER) || entry.value.includes(RED),
    );

    expect(signals, JSON.stringify(signals)).toEqual([]);
  });
});

test.describe('?id=<NO_REPOS>', () => {
  test('reads the empty-repositories message', async ({ page }) => {
    await page.goto(`/projects?id=${NO_REPOS_ID}`);

    await expect(page.getByTestId('projects-detail')).toContainText(
      'no repositories · edit the project to add one',
    );
  });
});

test.describe('an unknown ?id=', () => {
  test('renders the list with no detail pane and no crash', async ({ page }) => {
    const response = await page.goto(`/projects?id=${UNKNOWN_ID}`);

    expect(response?.status()).toBe(200);
    await expect(page.getByTestId('projects-detail')).toHaveCount(0);
  });
});

test.describe('/projects/{id}', () => {
  test('redirects to the ?id= form', async ({ request }) => {
    const response = await request.get(`/projects/${MIXED_ID}`, { maxRedirects: 0 });

    expect(response.status()).toBe(302);
    expect(response.headers()['location']).toBe(`/projects?id=${MIXED_ID}`);
  });
});
