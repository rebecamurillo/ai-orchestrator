import { expect, test, type Route } from '@playwright/test';

import { CLEAN_ID } from './projects-fixtures.mjs';

/**
 * The `slack` option on the Project channel form (story 3-2). As in `channel-form.spec.ts`,
 * the stub backend has no channel routes, so `page.route()` answers the island's proxy calls.
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

function json(route: Route, body: Json): Promise<void> {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

test('choosing slack pre-fills its Web API root, states the bot it needs, and saves', async ({
  page,
}) => {
  const puts: Json[] = [];
  await page.route(CHANNEL_URL, (route) => {
    const request = route.request();
    if (request.method() !== 'PUT') return json(route, OFF);
    const body = request.postDataJSON() as Json;
    puts.push(body);
    const stored: Json = { ...body, token_set: true };
    delete stored.token;
    return json(route, stored);
  });
  await page.goto(EDIT_URL);
  await expect(page.getByTestId('channel-provider')).toBeVisible();

  await page.getByTestId('channel-provider').selectOption('mattermost');
  await expect(page.getByTestId('channel-base-url')).toHaveValue('');
  await expect(page.getByTestId('channel-slack-note')).toHaveCount(0);

  await page.getByTestId('channel-provider').selectOption('slack');
  await expect(page.getByTestId('channel-base-url')).toHaveValue('https://slack.com/api');
  await expect(page.getByTestId('channel-slack-note')).toContainText('internal Slack app');
  await expect(page.getByTestId('channel-slack-note')).toContainText('chat:write');

  await page.getByTestId('channel-channel-id').fill('C0123ABC');
  await page.getByTestId('channel-allowed-users').fill('U01ANA ana');
  await page.getByTestId('channel-token-input').fill('xoxb-1');
  await page.getByTestId('channel-save').click();

  await expect(page.getByTestId('channel-token-state')).toContainText('set');
  expect(puts).toEqual([
    {
      provider: 'slack',
      base_url: 'https://slack.com/api',
      channel_id: 'C0123ABC',
      allowed_users: [{ id: 'U01ANA', handle: 'ana' }],
      metadata_only: false,
      token: 'xoxb-1',
    },
  ]);
  await expect(page.getByTestId('channel-provider')).toHaveValue('slack');
});
