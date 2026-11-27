import { expect, test, type Page } from '@playwright/test';

/**
 * Epic 11 flows beyond the per-story smoke (`initiative-page.spec.ts`): the request bodies the
 * page sends, Escape as the non-destructive action, and the states that render no writing
 * control. States the stub backend does not serve are made by rewriting its detail answer in
 * the browser, so this file owns its fixtures.
 */
const SPEC_STOP = '0193a000-0000-7000-8000-0000000000f1';
const BUILD_STOP = '0193a000-0000-7000-8000-0000000000f4';
const SPEC_RUN = '0193a000-0000-7000-8000-0000000000c1';
const BUILD_RUN = '0193a000-0000-7000-8000-0000000000c4';

type Detail = Record<string, unknown> & {
  workflows: { steps: { id: string; turns: Record<string, unknown>[] }[] }[];
};

async function rewriteDetail(page: Page, id: string, edit: (d: Detail) => void): Promise<void> {
  await page.route(new RegExp(`/api/initiatives/${id}(\\?.*)?$`), async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const response = await route.fetch();
    const body = (await response.json()) as Detail;
    edit(body);
    await route.fulfill({ response, json: body });
  });
}

test('the header and track read the current position', async ({ page }) => {
  await page.goto(`/initiatives/${SPEC_STOP}`);
  const header = page.getByTestId('ini-header');
  await expect(header.getByRole('link', { name: 'initiatives' })).toHaveAttribute(
    'href',
    '/initiatives',
  );
  await expect(header.getByRole('heading', { level: 1 })).toHaveText('familio-dessin-v2');
  await expect(header).toContainText('workflow 1 of 2 · spec · step 3 of 6');
  await expect(page.getByTestId('ini-workflow-spec')).toContainText('NOW');
  await expect(page.getByTestId('ini-workflow-spec')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('ini-workflow-build')).not.toContainText('NOW');
});

test('a past step opens read-only and the current step keeps its mark', async ({ page }) => {
  await page.goto(`/initiatives/${SPEC_STOP}`);
  await expect(page.getByTestId('ini-message')).toBeVisible();
  await page.getByTestId('ini-step-product').click();
  await expect(page.getByTestId('ini-message')).toHaveCount(0);
  await expect(page.getByTestId('ini-step-ux')).toHaveAttribute('aria-current', 'step');
  await expect(page.getByTestId('ini-step-product')).not.toHaveAttribute('aria-current', 'step');
});

test('?workflow=2 selects the auto workflow and links its Run page', async ({ page }) => {
  await page.goto(`/initiatives/${BUILD_STOP}?workflow=2`);
  await expect(page.getByTestId('ini-workflow-build')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('ini-steps')).toHaveCount(0);
  await expect(page.getByTestId('ini-open-workflow')).toHaveAttribute(
    'href',
    `/workflows/${BUILD_RUN}`,
  );
});

test('Start now posts start-next with the parked Run sequence', async ({ page }) => {
  await page.goto(`/initiatives/${SPEC_STOP}`);
  await page.getByTestId('ini-force-plan').click();
  const posted = page.waitForRequest(
    (r) => r.method() === 'POST' && r.url().endsWith(`/api/initiatives/${SPEC_STOP}/start-next`),
  );
  await page.getByTestId('ini-force-confirm').click();
  expect((await posted).postDataJSON()).toEqual({ park_seq: 7 });
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('Escape on the cancel confirmation keeps the initiative', async ({ page }) => {
  const cancels: string[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().endsWith('/cancel')) cancels.push(r.url());
  });
  await page.goto(`/initiatives/${SPEC_STOP}`);
  await page.getByTestId('ini-cancel').click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByTestId('ini-cancel')).toBeVisible();
  expect(cancels).toEqual([]);
});

test('reopen posts the chosen step and the build stop as the reason', async ({ page }) => {
  await page.goto(`/initiatives/${BUILD_STOP}?workflow=2`);
  await page.getByTestId('ini-reopen').click();
  await page.getByLabel('1.4 tech · tech-lead').check();
  const posted = page.waitForRequest(
    (r) => r.method() === 'POST' && r.url().endsWith(`/api/initiatives/${BUILD_STOP}/reopen`),
  );
  await page.getByTestId('ini-reopen-confirm').click();
  const body = (await posted).postDataJSON() as { step: string; reason: string };
  expect(body.step).toBe('tech');
  expect(body.reason).toContain('verify failed: make test exited 2');
});

test('Escape on the reopen modal sends nothing', async ({ page }) => {
  const reopens: string[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().endsWith('/reopen')) reopens.push(r.url());
  });
  await page.goto(`/initiatives/${BUILD_STOP}?workflow=2`);
  await page.getByTestId('ini-reopen').click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(reopens).toEqual([]);
});

test('a failed turn shows the red banner and Restart step retries the session', async ({
  page,
}) => {
  await rewriteDetail(page, SPEC_STOP, (d) => {
    Object.assign(d, { status: 'waiting for her', attention: 'blocked' });
    const ux = d.workflows[0].steps.find((s) => s.id === 'ux');
    const last = ux?.turns.at(-1);
    if (last) Object.assign(last, { status: 'failed', failure_reason: 'harness exited 1' });
  });
  await page.goto(`/initiatives/${SPEC_STOP}`);
  await expect(page.getByTestId('ini-stop')).toContainText('harness exited 1');
  const posted = page.waitForRequest(
    (r) => r.method() === 'POST' && r.url().endsWith(`/api/runs/${SPEC_RUN}/session/retry`),
  );
  await page.getByTestId('ini-restart').click();
  await posted;
});

test('a cancelled initiative renders no control that writes', async ({ page }) => {
  await rewriteDetail(page, SPEC_STOP, (d) => {
    Object.assign(d, { status: 'cancelled', cancelled_at: '2026-11-25T10:00:00Z' });
  });
  await page.goto(`/initiatives/${SPEC_STOP}`);
  await expect(page.getByTestId('ini-header')).toContainText('cancelled at ux');
  await expect(page.getByTestId('ini-workflows')).not.toContainText('NOW');
  await expect(page.getByTestId('ini-cancel')).toHaveCount(0);
  await expect(page.getByTestId('ini-force-plan')).toHaveCount(0);
  await expect(page.getByTestId('ini-message')).toHaveCount(0);
});

test('a done initiative reads its merge date and offers no cancel', async ({ page }) => {
  await rewriteDetail(page, SPEC_STOP, (d) => {
    Object.assign(d, { status: 'done', pr_merged_at: '2026-11-25T10:00:00Z' });
  });
  await page.goto(`/initiatives/${SPEC_STOP}`);
  await expect(page.getByTestId('ini-header')).toContainText(
    'done · pull request merged 2026-11-25',
  );
  await expect(page.getByTestId('ini-cancel')).toHaveCount(0);
  await expect(page.getByTestId('ini-stop')).toHaveCount(0);
});

test('a refused detail read shows the failed fetch with a retry', async ({ page }) => {
  await page.route(new RegExp(`/api/initiatives/${SPEC_STOP}(\\?.*)?$`), (route) =>
    route.fulfill({
      status: 404,
      contentType: 'application/problem+json',
      body: JSON.stringify({ type: 'about:blank', title: 'not found', status: 404 }),
    }),
  );
  await page.goto(`/initiatives/${SPEC_STOP}`);
  await expect(page.getByTestId('fetch-failed')).toBeVisible();
  await expect(page.getByTestId('fetch-retry')).toBeVisible();
  await expect(page.getByTestId('initiative-page')).toHaveCount(0);
});
