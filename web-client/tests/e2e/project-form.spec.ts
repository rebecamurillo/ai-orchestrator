import { expect, test, type Page } from '@playwright/test';

import {
  NO_QUALITY_COMMAND_REPOSITORY_URL,
  UNREACHABLE_REPOSITORY_URL,
} from './projects-fixtures.mjs';

/**
 * The New/Edit project form and its live **CLONE CHECK** readout (2.5), end to end against
 * the extended stub backend (`stub-backend.mjs`): every scenario here creates and edits a
 * real Project through the form itself, rather than reading a stored fixture, because the
 * story's own save flow — one `POST`/`PUT` per resource, an explicit clone-check per
 * Repository, then a final read — is exactly what these routes exist to prove.
 *
 * `fullyParallel: true` is safe here with no dedicated fixture ids (unlike `projects.spec.ts`
 * (2.4)): every test creates its own Project through the stub's generated ids, so nothing
 * two tests touch can collide.
 */

const REPO_URL = (label: string) => `https://github.com/example/${label}-${Date.now()}.git`;

async function fillProjectName(page: Page, name: string): Promise<void> {
  await page.getByTestId('project-form-name').fill(name);
}

async function addRepositoryRow(
  page: Page,
  index: number,
  fields: { url: string; defaultBranch?: string; quality?: string },
): Promise<void> {
  await page.getByTestId('project-form-repo-add').click();
  await page.getByTestId(`repo-form-${index}-url`).fill(fields.url);
  if (fields.defaultBranch !== undefined) {
    await page.getByTestId(`repo-form-${index}-default-branch`).fill(fields.defaultBranch);
  }
  if (fields.quality !== undefined) {
    await page.getByTestId(`repo-form-${index}-quality`).fill(fields.quality);
  }
}

async function addEnvVarRow(
  page: Page,
  index: number,
  fields: { name: string; value: string },
): Promise<void> {
  await page.getByTestId('project-form-env-add').click();
  await page.getByTestId(`project-form-env-${index}-name`).fill(fields.name);
  await page.getByTestId(`project-form-env-${index}-value`).fill(fields.value);
}

async function save(page: Page): Promise<void> {
  await page.getByTestId('project-form-save').click();
}

test.describe('/projects/new', () => {
  test('creating two repositories and one env var shows the readout and redirects to edit?saved=1', async ({
    page,
  }) => {
    await page.goto('/projects/new');
    await fillProjectName(page, 'Mixed Signals E2E');
    await addRepositoryRow(page, 0, {
      url: REPO_URL('api'),
      defaultBranch: 'main',
      quality: 'pnpm lint && pnpm test',
    });
    await addRepositoryRow(page, 1, {
      url: REPO_URL('web'),
      defaultBranch: 'main',
      quality: 'pnpm lint && pnpm test',
    });
    await addEnvVarRow(page, 0, { name: 'NODE_ENV', value: 'production' });

    await Promise.all([page.waitForURL(/\/projects\/.+\/edit\?saved=1$/), save(page)]);

    const blocks = page.locator('[data-testid^="projects-clone-check-"]');
    await expect(blocks).toHaveCount(2);
    for (const block of await blocks.all()) {
      await expect(block).toContainText('ls-remote');
      await expect(block).toContainText('clone');
      await expect(block).toContainText('default branch');
      await expect(block).toContainText('method version');
      await expect(block).toContainText('ok');
    }
  });

  test('an empty default branch on the second repository keeps every value and prints the reason beside it', async ({
    page,
  }) => {
    await page.goto('/projects/new');
    await fillProjectName(page, 'Keeps Every Value');
    const firstUrl = REPO_URL('first');
    const secondUrl = REPO_URL('second');
    await addRepositoryRow(page, 0, { url: firstUrl, defaultBranch: 'main' });
    await addRepositoryRow(page, 1, { url: secondUrl });

    await save(page);
    await page.waitForLoadState('networkidle');

    expect(new URL(page.url()).pathname).toBe('/projects/new');
    await expect(page.getByTestId('repo-form-1-default-branch-error')).toContainText('required');
    await expect(page.getByTestId('project-form-name')).toHaveValue('Keeps Every Value');
    await expect(page.getByTestId('repo-form-0-url')).toHaveValue(firstUrl);
    await expect(page.getByTestId('repo-form-1-url')).toHaveValue(secondUrl);
  });

  test('a repository the token cannot reach is saved anyway, its readout showing the failure', async ({
    page,
  }) => {
    await page.goto('/projects/new');
    await fillProjectName(page, 'Unreachable Token');
    await addRepositoryRow(page, 0, {
      url: UNREACHABLE_REPOSITORY_URL,
      defaultBranch: 'main',
      quality: 'pnpm test',
    });

    await Promise.all([page.waitForURL(/\/projects\/.+\/edit\?saved=1$/), save(page)]);

    const block = page.locator('[data-testid^="projects-clone-check-"]').first();
    await expect(block).toContainText('ls-remote');
    await expect(block).toContainText('failed');
    await expect(block).toContainText('terminal prompts disabled');
    await expect(block).toContainText('add a deploy key or a GITHUB_TOKEN');
    await expect(block).toContainText('failed · new runs blocked');
  });

  test('a repository with no quality_gate_command ends the block with "verify step will be skipped"', async ({
    page,
  }) => {
    await page.goto('/projects/new');
    await fillProjectName(page, 'No Quality Gate');
    await addRepositoryRow(page, 0, {
      url: NO_QUALITY_COMMAND_REPOSITORY_URL,
      defaultBranch: 'main',
    });

    await Promise.all([page.waitForURL(/\/projects\/.+\/edit\?saved=1$/), save(page)]);

    const block = page.locator('[data-testid^="projects-clone-check-"]').first();
    await expect(block).toContainText('verify step will be skipped');
  });

  test('has no token or gateway key field, and states credentials are an instance setting', async ({
    page,
  }) => {
    await page.goto('/projects/new');

    await expect(page.getByText('credentials are instance settings (.env)')).toBeVisible();
    const tokenLocators = await page.locator('[data-testid*="token"]').count();
    expect(tokenLocators).toBe(0);
    const gatewayLocators = await page.locator('[data-testid*="gateway"]').count();
    expect(gatewayLocators).toBe(0);
  });

  test('the log_prompt_content switch reveals and hides the Langfuse disclosure line, and the checked state is saved', async ({
    page,
  }) => {
    await page.goto('/projects/new');
    const disclosure = page.getByText(
      'on: prompt and tool content, including source code, is sent to Langfuse for this project',
    );

    await expect(disclosure).toHaveCount(0);

    const toggle = page.getByTestId('project-form-log-prompt-content');
    await toggle.check();
    await expect(disclosure).toBeVisible();

    await toggle.uncheck();
    await expect(disclosure).toHaveCount(0);

    await fillProjectName(page, 'Log Prompt Content On');
    await addRepositoryRow(page, 0, { url: REPO_URL('log-prompt'), defaultBranch: 'main' });
    await toggle.check();

    await Promise.all([page.waitForURL(/\/projects\/.+\/edit\?saved=1$/), save(page)]);

    // a fresh load of the edit page reflects the stored switch, not just the pre-submit DOM
    await expect(page.getByTestId('project-form-log-prompt-content')).toBeChecked();
    await expect(disclosure).toBeVisible();
  });
});

test.describe('editing a stored env var', () => {
  test('is unchanged when saved untouched, and its mask changes after replace', async ({
    page,
  }) => {
    await page.goto('/projects/new');
    await fillProjectName(page, 'Env Var Round Trip');
    await addRepositoryRow(page, 0, { url: REPO_URL('kept'), defaultBranch: 'main' });
    await addEnvVarRow(page, 0, { name: 'API_KEY', value: 'first-secret-value' });

    await Promise.all([page.waitForURL(/\/projects\/.+\/edit\?saved=1$/), save(page)]);

    const originalMask = await page.getByTestId('project-form-env-0-masked').textContent();
    expect(originalMask).toContain('alue');

    // saved without touching the env var: the stored value and its mask are unchanged
    await Promise.all([page.waitForURL(/\/projects\/.+\/edit\?saved=1$/), save(page)]);
    await expect(page.getByTestId('project-form-env-0-masked')).toHaveText(originalMask ?? '');

    // *replace*, a new value, save: the mask changes
    await page.getByTestId('project-form-env-0-replace').click();
    await page.getByTestId('project-form-env-0-value').fill('a-different-secret-999');
    await Promise.all([page.waitForURL(/\/projects\/.+\/edit\?saved=1$/), save(page)]);

    const replacedMask = await page.getByTestId('project-form-env-0-masked').textContent();
    expect(replacedMask).not.toBe(originalMask);
    expect(replacedMask).toContain('999');
  });
});
