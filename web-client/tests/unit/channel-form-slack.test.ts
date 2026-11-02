// @vitest-environment jsdom
/**
 * The `slack` option on the Project channel form (story 3-2, step two): choosing it pre-fills
 * an empty base URL with Slack's Web API root, `mattermost` pre-fills nothing, and a Slack
 * channel shows what the bot needs. The pure rule is `chooseProvider` in
 * `src/lib/projects/channel.ts`; the island is mounted against a mocked `src/api/client.ts`.
 */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { components } from '../../src/api/schema';
import {
  SLACK_BASE_URL,
  SLACK_NOTE,
  bodyFromForm,
  chooseProvider,
  formFromChannel,
  guarded,
} from '../../src/lib/projects/channel';

type ChannelOut = components['schemas']['ChannelOut'];

const { GET, PUT, POST } = vi.hoisted(() => ({ GET: vi.fn(), PUT: vi.fn(), POST: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET, PUT, POST } }));

import ChannelForm from '../../src/islands/ChannelForm';

const OFF: ChannelOut = {
  provider: 'off',
  base_url: null,
  channel_id: null,
  token_set: false,
  allowed_users: [],
  metadata_only: false,
};

const SLACK: ChannelOut = {
  provider: 'slack',
  base_url: SLACK_BASE_URL,
  channel_id: 'C0123ABC',
  token_set: true,
  allowed_users: [{ id: 'U01ANA', handle: 'ana' }],
  metadata_only: false,
};

function ok(data: unknown) {
  return { data, response: { status: 200 } };
}

async function mount(initial: ChannelOut) {
  GET.mockResolvedValueOnce(ok(initial));
  render(createElement(ChannelForm, { projectId: 'p-1' }));
  await screen.findByTestId('channel-provider');
}

function field(id: string): HTMLInputElement {
  return screen.getByTestId(id) as HTMLInputElement;
}

function choose(provider: string) {
  fireEvent.change(field('channel-provider'), { target: { value: provider } });
}

beforeEach(() => {
  GET.mockReset();
  PUT.mockReset();
  POST.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('guarded', () => {
  it('answers the call, or a bodiless refusal when the call throws', async () => {
    await expect(guarded(() => Promise.resolve({ data: 1 }))).resolves.toEqual({ data: 1 });
    await expect(guarded(() => Promise.reject(new Error('offline')))).resolves.toEqual({
      error: undefined,
    });
  });
});

describe('chooseProvider', () => {
  const blank = formFromChannel(OFF);

  it('pre-fills Slack’s Web API root when the base URL is empty', () => {
    expect(SLACK_BASE_URL).toBe('https://slack.com/api');
    expect(chooseProvider(blank, 'slack')).toEqual({
      provider: 'slack',
      baseUrl: 'https://slack.com/api',
    });
    expect(chooseProvider({ ...blank, baseUrl: '   ' }, 'slack')).toEqual({
      provider: 'slack',
      baseUrl: 'https://slack.com/api',
    });
  });

  it('keeps a base URL the Operator already typed', () => {
    const typed = { ...blank, baseUrl: 'https://slack-gov.com/api' };
    expect(chooseProvider(typed, 'slack')).toEqual({ provider: 'slack' });
  });

  it('pre-fills nothing for mattermost or off', () => {
    expect(chooseProvider(blank, 'mattermost')).toEqual({ provider: 'mattermost' });
    expect(chooseProvider(blank, 'off')).toEqual({ provider: 'off' });
  });

  it('builds a slack body like any other provider', () => {
    const built = bodyFromForm({
      ...formFromChannel(SLACK),
      replacingToken: true,
      token: 'xoxb-1',
    });
    expect(built).toEqual({
      ok: true,
      body: {
        provider: 'slack',
        base_url: 'https://slack.com/api',
        channel_id: 'C0123ABC',
        allowed_users: [{ id: 'U01ANA', handle: 'ana' }],
        metadata_only: false,
        token: 'xoxb-1',
      },
    });
  });
});

describe('the form', () => {
  it('offers off, mattermost and slack', async () => {
    await mount(OFF);
    const options = Array.from(field('channel-provider').querySelectorAll('option'));
    expect(options.map((option) => option.value)).toEqual(['off', 'mattermost', 'slack']);
  });

  it('pre-fills the base URL on choosing slack, and not on choosing mattermost', async () => {
    await mount(OFF);
    choose('mattermost');
    expect(field('channel-base-url').value).toBe('');
    choose('slack');
    expect(field('channel-base-url').value).toBe('https://slack.com/api');
  });

  it('keeps a typed base URL when slack is chosen', async () => {
    await mount(OFF);
    choose('mattermost');
    fireEvent.change(field('channel-base-url'), { target: { value: 'https://slack-gov.com/api' } });
    choose('slack');
    expect(field('channel-base-url').value).toBe('https://slack-gov.com/api');
  });

  it('states what a Slack bot needs, only for a Slack channel', async () => {
    await mount(SLACK);
    expect(screen.getByTestId('channel-slack-note').textContent).toBe(SLACK_NOTE);
    expect(SLACK_NOTE).toBe(
      'the bot must be an internal Slack app, invited to the channel, with scopes chat:write, ' +
        'channels:history and channels:read (groups:history and groups:read for a private channel)',
    );
    choose('mattermost');
    expect(screen.queryByTestId('channel-slack-note')).toBeNull();
    choose('off');
    expect(screen.queryByTestId('channel-slack-note')).toBeNull();
  });

  it('saves a new slack channel with the pre-filled base URL', async () => {
    await mount(OFF);
    PUT.mockResolvedValueOnce(ok(SLACK));
    choose('slack');
    fireEvent.change(field('channel-channel-id'), { target: { value: 'C0123ABC' } });
    fireEvent.change(field('channel-allowed-users'), { target: { value: 'U01ANA ana' } });
    fireEvent.change(field('channel-token-input'), { target: { value: 'xoxb-1' } });
    fireEvent.click(screen.getByTestId('channel-save'));
    await screen.findByTestId('channel-saved');
    expect(PUT.mock.calls[0]![1].body).toEqual({
      provider: 'slack',
      base_url: 'https://slack.com/api',
      channel_id: 'C0123ABC',
      allowed_users: [{ id: 'U01ANA', handle: 'ana' }],
      metadata_only: false,
      token: 'xoxb-1',
    });
  });
});
