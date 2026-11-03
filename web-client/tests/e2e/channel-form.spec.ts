import { expect, test, type Page, type Route } from '@playwright/test';

import { CLEAN_ID } from './projects-fixtures.mjs';

/**
 * The Project channel form (story 3-5) on `/projects/<id>/edit`. The stub backend has no
 * `/projects/{id}/channel` routes, so the island's browser calls — which go through the
 * same-origin proxy as `/api/projects/<id>/channel[/test]` — are answered by `page.route()`
 * mocks the spec installs before the page opens.
 */

const EDIT_URL = `/projects/${CLEAN_ID}/edit`;
const CHANNEL_URL = /\/api\/projects\/[^/]+\/channel(\/test)?$/;

type Json = Record<string, unknown>;

const OFF: Json = {
  provider: 'off',
  base_url: null,
  channel_id: null,
  token_set: false,
  allowed_users: [],
  metadata_only: false,
};

const SET: Json = {
  provider: 'mattermost',
  base_url: 'https://chat.example.com',
  channel_id: 'chan1',
  token_set: true,
  allowed_users: [
    { id: 'u1', handle: 'alice' },
    { id: 'u2', handle: 'bob' },
  ],
  metadata_only: false,
};

interface Seen {
  puts: Json[];
  tests: number;
}

interface Answers {
  get: Json;
  put?: (body: Json) => { status: number; body: Json };
  test?: { status: number; body: Json };
}

function json(route: Route, status: number, body: Json): Promise<void> {
  return route.fulfill({
    status,
    contentType: status === 200 ? 'application/json' : 'application/problem+json',
    body: JSON.stringify(body),
  });
}

async function mockChannel(page: Page, answers: Answers): Promise<Seen> {
  const seen: Seen = { puts: [], tests: 0 };
  await page.route(CHANNEL_URL, (route) => {
    const request = route.request();
    if (request.url().endsWith('/test')) {
      seen.tests += 1;
      const answer = answers.test ?? { status: 200, body: { ok: true, detail: 'connected' } };
      return json(route, answer.status, answer.body);
    }
    if (request.method() === 'PUT') {
      const body = request.postDataJSON() as Json;
      seen.puts.push(body);
      const answer = answers.put?.(body) ?? { status: 200, body: SET };
      return json(route, answer.status, answer.body);
    }
    return json(route, 200, answers.get);
  });
  return seen;
}

async function open(page: Page): Promise<void> {
  await page.goto(EDIT_URL);
  await expect(page.getByTestId('channel-provider')).toBeVisible();
}

test.describe('Project channel form', () => {
  test('an off channel hides the fields and disables Test', async ({ page }) => {
    await mockChannel(page, { get: OFF });
    await open(page);

    await expect(page.getByTestId('channel-provider')).toHaveValue('off');
    await expect(page.getByTestId('channel-base-url')).toHaveCount(0);
    await expect(page.getByTestId('channel-test')).toBeDisabled();
    await expect(page.getByTestId('channel-note')).toHaveText(
      'the bot token is stored encrypted, never shown, and never given to an agent',
    );
  });

  test('saving a new channel sends the token once, then reads `set` and allows Test', async ({
    page,
  }) => {
    const seen = await mockChannel(page, { get: OFF });
    await open(page);

    await page.getByTestId('channel-provider').selectOption('mattermost');
    await page.getByTestId('channel-base-url').fill('https://chat.example.com');
    await page.getByTestId('channel-channel-id').fill('chan1');
    await page.getByTestId('channel-allowed-users').fill('u1 alice\nu2 bob');
    await page.getByTestId('channel-token-input').fill('bot-secret');
    await page.getByTestId('channel-save').click();

    await expect(page.getByTestId('channel-token-state')).toContainText('set');
    await expect(page.getByTestId('channel-token-input')).toHaveCount(0);
    expect(seen.puts).toHaveLength(1);
    expect(seen.puts[0]).toMatchObject({
      provider: 'mattermost',
      token: 'bot-secret',
      allowed_users: [
        { id: 'u1', handle: 'alice' },
        { id: 'u2', handle: 'bob' },
      ],
    });
    await expect(page.getByTestId('channel-test')).toBeEnabled();
  });

  test('saving without pressing replace sends no token key', async ({ page }) => {
    const seen = await mockChannel(page, { get: SET });
    await open(page);

    await page.getByTestId('channel-channel-id').fill('chan2');
    await page.getByTestId('channel-save').click();

    await expect(page.getByTestId('channel-saved')).toBeVisible();
    expect(seen.puts).toHaveLength(1);
    expect(Object.keys(seen.puts[0]!)).not.toContain('token');
  });

  test('cancel after replace hides the input and reads `set` again', async ({ page }) => {
    const seen = await mockChannel(page, { get: SET });
    await open(page);

    await page.getByTestId('channel-token-replace').click();
    await page.getByTestId('channel-token-input').fill('half-typed');
    await page.getByTestId('channel-token-cancel').click();

    await expect(page.getByTestId('channel-token-input')).toHaveCount(0);
    await expect(page.getByTestId('channel-token-state')).toContainText('set');
    await page.getByTestId('channel-channel-id').fill('chan2');
    await page.getByTestId('channel-save').click();
    await expect(page.getByTestId('channel-saved')).toBeVisible();
    expect(Object.keys(seen.puts[0]!)).not.toContain('token');
  });

  test('a failed probe shows `failed` and the platform text beside the button', async ({
    page,
  }) => {
    const seen = await mockChannel(page, {
      get: SET,
      test: { status: 200, body: { ok: false, detail: '401 Invalid or expired session' } },
    });
    await open(page);

    await page.getByTestId('channel-test').click();

    await expect(page.getByTestId('channel-test-status')).toHaveText('failed');
    await expect(page.getByTestId('channel-test-detail')).toHaveText(
      '401 Invalid or expired session',
    );
    expect(seen.tests).toBe(1);
  });

  test('an edit after the save disables Test and says to save first', async ({ page }) => {
    await mockChannel(page, { get: SET });
    await open(page);
    await expect(page.getByTestId('channel-test')).toBeEnabled();

    await page.getByTestId('channel-channel-id').fill('chan2');

    await expect(page.getByTestId('channel-test')).toBeDisabled();
    await expect(page.getByTestId('channel-dirty-line')).toHaveText('save before testing');
  });

  test('a kept token meeting a new host shows the refusal detail', async ({ page }) => {
    await mockChannel(page, {
      get: SET,
      put: () => ({
        status: 422,
        body: {
          title: 'invalid',
          status: 422,
          detail: 'token: enter the token again when the host changes',
        },
      }),
    });
    await open(page);

    await page.getByTestId('channel-base-url').fill('https://other.example.com');
    await page.getByTestId('channel-save').click();

    await expect(page.getByTestId('channel-error')).toHaveText(
      'token: enter the token again when the host changes',
    );
  });

  test('a field refusal prints its reason at the field', async ({ page }) => {
    await mockChannel(page, {
      get: SET,
      put: () => ({
        status: 422,
        body: {
          title: 'validation failed',
          status: 422,
          errors: [{ path: 'body.base_url', reason: 'a base URL is http(s)://host' }],
        },
      }),
    });
    await open(page);

    await page.getByTestId('channel-base-url').fill('ftp://nope');
    await page.getByTestId('channel-save').click();

    await expect(page.getByTestId('channel-base-url-error')).toHaveText(
      'a base URL is http(s)://host',
    );
  });

  test('a malformed allowed-users line is refused in the form with no request', async ({
    page,
  }) => {
    const seen = await mockChannel(page, { get: SET });
    await open(page);

    await page.getByTestId('channel-allowed-users').fill('u1');
    await page.getByTestId('channel-save').click();

    await expect(page.getByTestId('channel-allowed-users-error')).toContainText('line 1');
    expect(seen.puts).toHaveLength(0);
  });

  test('/projects/new carries no channel-* test id', async ({ page }) => {
    await page.goto('/projects/new');
    await expect(page.getByTestId('project-form')).toBeVisible();
    await expect(page.locator('[data-testid^="channel-"]')).toHaveCount(0);
  });
});
