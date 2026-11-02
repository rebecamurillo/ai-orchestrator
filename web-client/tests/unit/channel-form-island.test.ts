// @vitest-environment jsdom
/**
 * `ChannelForm.tsx` (story 3-5), mounted with React Testing Library against a mocked
 * `src/api/client.ts` — the island's only fetch caller (AD-1). `openapi-fetch` cannot build a
 * `Request` from a relative base URL outside a browser, so the client is replaced rather than
 * its transport. Its behaviour over the real proxy is `tests/e2e/channel-form.spec.ts`.
 */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { components } from '../../src/api/schema';

type ChannelOut = components['schemas']['ChannelOut'];

const { GET, PUT, POST } = vi.hoisted(() => ({ GET: vi.fn(), PUT: vi.fn(), POST: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET, PUT, POST } }));

import ChannelForm from '../../src/islands/ChannelForm';

const PROJECT_ID = 'p-1';
const CHANNEL_PATH = '/projects/{project_id}/channel';
const TEST_PATH = '/projects/{project_id}/channel/test';

const OFF: ChannelOut = {
  provider: 'off',
  base_url: null,
  channel_id: null,
  token_set: false,
  allowed_users: [],
  metadata_only: false,
};

const SET: ChannelOut = {
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

function ok(data: unknown) {
  return { data, response: { status: 200 } };
}

function problem(status: number, body: Record<string, unknown>) {
  return { error: { title: 'problem', status, ...body }, response: { status } };
}

async function mount(initial: ChannelOut) {
  GET.mockResolvedValueOnce(ok(initial));
  render(createElement(ChannelForm, { projectId: PROJECT_ID }));
  await screen.findByTestId('channel-provider');
}

function field(id: string): HTMLInputElement {
  return screen.getByTestId(id) as HTMLInputElement;
}

function type(id: string, value: string) {
  fireEvent.change(field(id), { target: { value } });
}

async function fillNewChannel() {
  fireEvent.change(field('channel-provider'), { target: { value: 'mattermost' } });
  type('channel-base-url', 'https://chat.example.com');
  type('channel-channel-id', 'chan1');
  type('channel-allowed-users', 'u1 alice\nu2 bob');
  type('channel-token-input', 'bot-secret');
}

beforeEach(() => {
  GET.mockReset();
  PUT.mockReset();
  POST.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('loading', () => {
  it('reads the channel for the Project through the shared client', async () => {
    await mount(OFF);
    expect(GET).toHaveBeenCalledWith(CHANNEL_PATH, {
      params: { path: { project_id: PROJECT_ID } },
    });
  });

  it('shows an off channel: the select reads off, the fields are hidden, Test is disabled', async () => {
    await mount(OFF);
    expect(field('channel-provider').value).toBe('off');
    expect(screen.queryByTestId('channel-base-url')).toBeNull();
    expect(screen.queryByTestId('channel-channel-id')).toBeNull();
    expect(screen.queryByTestId('channel-allowed-users')).toBeNull();
    expect(screen.queryByTestId('channel-token-state')).toBeNull();
    expect((screen.getByTestId('channel-test') as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows a set channel with its fields filled and the token as `set` with a replace control', async () => {
    await mount(SET);
    expect(field('channel-provider').value).toBe('mattermost');
    expect(field('channel-base-url').value).toBe('https://chat.example.com');
    expect(field('channel-channel-id').value).toBe('chan1');
    expect(field('channel-allowed-users').value).toBe('u1 alice\nu2 bob');
    expect(screen.getByTestId('channel-token-state').textContent).toContain('set');
    expect(screen.queryByTestId('channel-token-input')).toBeNull();
    expect((screen.getByTestId('channel-test') as HTMLButtonElement).disabled).toBe(false);
  });

  it('reveals an empty password input when replace is pressed', async () => {
    await mount(SET);
    fireEvent.click(screen.getByTestId('channel-token-replace'));
    const input = field('channel-token-input');
    expect(input.type).toBe('password');
    expect(input.value).toBe('');
  });

  it('states what happens to the bot token', async () => {
    await mount(SET);
    expect(screen.getByTestId('channel-note').textContent).toBe(
      'the bot token is stored encrypted, never shown, and never given to an agent',
    );
  });

  it('shows a failed read with its problem detail and a retry that reads again', async () => {
    GET.mockResolvedValueOnce(problem(404, { detail: 'No Project has that id.' }));
    render(createElement(ChannelForm, { projectId: PROJECT_ID }));
    const line = await screen.findByTestId('channel-load-error');
    expect(line.textContent).toContain('No Project has that id.');

    GET.mockResolvedValueOnce(ok(SET));
    fireEvent.click(screen.getByTestId('channel-retry'));
    await screen.findByTestId('channel-provider');
    expect(GET).toHaveBeenCalledTimes(2);
    expect(screen.queryByTestId('channel-load-error')).toBeNull();
  });

  it('shows a transport failure as a failed read', async () => {
    GET.mockRejectedValueOnce(new TypeError('fetch failed'));
    render(createElement(ChannelForm, { projectId: PROJECT_ID }));
    expect((await screen.findByTestId('channel-load-error')).textContent).toContain(
      'request failed',
    );
  });
});

describe('saving', () => {
  it('sends the typed token on a new channel and afterwards reads `set` with no token held', async () => {
    await mount(OFF);
    await fillNewChannel();
    PUT.mockResolvedValueOnce(ok({ ...SET }));
    fireEvent.click(screen.getByTestId('channel-save'));

    await waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));
    expect(PUT).toHaveBeenCalledWith(CHANNEL_PATH, {
      params: { path: { project_id: PROJECT_ID } },
      body: {
        provider: 'mattermost',
        base_url: 'https://chat.example.com',
        channel_id: 'chan1',
        allowed_users: [
          { id: 'u1', handle: 'alice' },
          { id: 'u2', handle: 'bob' },
        ],
        metadata_only: false,
        token: 'bot-secret',
      },
    });
    await waitFor(() =>
      expect(screen.getByTestId('channel-token-state').textContent).toContain('set'),
    );
    expect(screen.queryByTestId('channel-token-input')).toBeNull();
    expect(document.body.innerHTML).not.toContain('bot-secret');
    expect(screen.getByTestId('channel-saved')).toBeTruthy();
  });

  it('sends no token key when the stored token was not replaced', async () => {
    await mount(SET);
    type('channel-channel-id', 'chan2');
    PUT.mockResolvedValueOnce(ok({ ...SET, channel_id: 'chan2' }));
    fireEvent.click(screen.getByTestId('channel-save'));

    await waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));
    const body = PUT.mock.calls[0]![1].body as Record<string, unknown>;
    expect('token' in body).toBe(false);
    expect(body.channel_id).toBe('chan2');
  });

  it('sends the typed token after replace and clears it once saved', async () => {
    await mount(SET);
    fireEvent.click(screen.getByTestId('channel-token-replace'));
    type('channel-token-input', 'rotated');
    PUT.mockResolvedValueOnce(ok(SET));
    fireEvent.click(screen.getByTestId('channel-save'));

    await waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));
    expect((PUT.mock.calls[0]![1].body as { token: string }).token).toBe('rotated');
    await waitFor(() => expect(screen.queryByTestId('channel-token-input')).toBeNull());
    expect(document.body.innerHTML).not.toContain('rotated');
  });

  it('turns the channel off with a bare provider and disables Test', async () => {
    await mount(SET);
    fireEvent.change(field('channel-provider'), { target: { value: 'off' } });
    PUT.mockResolvedValueOnce(ok(OFF));
    fireEvent.click(screen.getByTestId('channel-save'));

    await waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));
    expect(PUT.mock.calls[0]![1].body).toEqual({ provider: 'off' });
    await waitFor(() => expect(screen.queryByTestId('channel-base-url')).toBeNull());
    expect((screen.getByTestId('channel-test') as HTMLButtonElement).disabled).toBe(true);
  });

  it('refuses a malformed allowed-users line inline and sends nothing', async () => {
    await mount(SET);
    type('channel-allowed-users', 'u1 alice\nu2');
    fireEvent.click(screen.getByTestId('channel-save'));

    expect((await screen.findByTestId('channel-allowed-users-error')).textContent).toContain(
      'line 2',
    );
    expect(PUT).not.toHaveBeenCalled();
  });

  it('shows each 422 errors[].path at its field', async () => {
    await mount(SET);
    type('channel-base-url', 'ftp://nope');
    PUT.mockResolvedValueOnce(
      problem(422, {
        detail: 'body.base_url: a base URL is http(s)://host, with no whitespace',
        errors: [
          { path: 'body.base_url', reason: 'a base URL is http(s)://host, with no whitespace' },
          { path: 'body.channel_id', reason: 'a channel id is non-empty, with no whitespace' },
        ],
      }),
    );
    fireEvent.click(screen.getByTestId('channel-save'));

    expect((await screen.findByTestId('channel-base-url-error')).textContent).toBe(
      'a base URL is http(s)://host, with no whitespace',
    );
    expect(screen.getByTestId('channel-channel-id-error').textContent).toContain('channel id');
    expect(screen.queryByTestId('channel-error')).toBeNull();
  });

  it('shows the detail of a 422 that names no field when a kept token meets a new host', async () => {
    await mount(SET);
    type('channel-base-url', 'https://other.example.com');
    PUT.mockResolvedValueOnce(
      problem(422, { detail: 'token: enter the token again when the host changes' }),
    );
    fireEvent.click(screen.getByTestId('channel-save'));

    expect((await screen.findByTestId('channel-error')).textContent).toBe(
      'token: enter the token again when the host changes',
    );
  });

  it('shows the detail of a 409 for a built-in Project', async () => {
    await mount(SET);
    type('channel-channel-id', 'chan2');
    PUT.mockResolvedValueOnce(problem(409, { detail: 'the readiness Project cannot be edited' }));
    fireEvent.click(screen.getByTestId('channel-save'));

    expect((await screen.findByTestId('channel-error')).textContent).toBe(
      'the readiness Project cannot be edited',
    );
  });

  it('keeps the form dirty and the typed token after a refused save', async () => {
    await mount(SET);
    fireEvent.click(screen.getByTestId('channel-token-replace'));
    type('channel-token-input', 'typed');
    PUT.mockResolvedValueOnce(problem(422, { detail: 'refused' }));
    fireEvent.click(screen.getByTestId('channel-save'));

    await screen.findByTestId('channel-error');
    expect(field('channel-token-input').value).toBe('typed');
    expect((screen.getByTestId('channel-test') as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('testing', () => {
  it('posts the probe for the saved channel and shows `failed` and its detail beside the button', async () => {
    await mount(SET);
    POST.mockResolvedValueOnce(ok({ ok: false, detail: '401 Invalid or expired session' }));
    fireEvent.click(screen.getByTestId('channel-test'));

    await waitFor(() =>
      expect(screen.getByTestId('channel-test-status').textContent).toBe('failed'),
    );
    expect(screen.getByTestId('channel-test-detail').textContent).toBe(
      '401 Invalid or expired session',
    );
    expect(POST).toHaveBeenCalledWith(TEST_PATH, {
      params: { path: { project_id: PROJECT_ID } },
    });
  });

  it('shows `ok` and the connected line', async () => {
    await mount(SET);
    POST.mockResolvedValueOnce(ok({ ok: true, detail: 'connected as @orchestrator' }));
    fireEvent.click(screen.getByTestId('channel-test'));

    await waitFor(() => expect(screen.getByTestId('channel-test-status').textContent).toBe('ok'));
    expect(screen.getByTestId('channel-test-detail').textContent).toBe(
      'connected as @orchestrator',
    );
  });

  it('shows an undecryptable stored token verbatim', async () => {
    const detail =
      'the stored token cannot be decrypted with the current key; save the token again';
    await mount(SET);
    POST.mockResolvedValueOnce(ok({ ok: false, detail }));
    fireEvent.click(screen.getByTestId('channel-test'));

    await waitFor(() => expect(screen.getByTestId('channel-test-detail').textContent).toBe(detail));
  });

  it('shows the problem detail of a non-200 answer', async () => {
    await mount(SET);
    POST.mockResolvedValueOnce(problem(409, { detail: 'no channel is set' }));
    fireEvent.click(screen.getByTestId('channel-test'));

    await waitFor(() =>
      expect(screen.getByTestId('channel-test-detail').textContent).toBe('no channel is set'),
    );
    expect(screen.getByTestId('channel-test-status').textContent).toBe('failed');
  });

  it('disables Test with a `save before testing` line while the form has unsaved changes', async () => {
    await mount(SET);
    expect(screen.queryByTestId('channel-dirty-line')).toBeNull();

    type('channel-channel-id', 'chan2');
    expect((screen.getByTestId('channel-test') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId('channel-dirty-line').textContent).toBe('save before testing');

    PUT.mockResolvedValueOnce(ok({ ...SET, channel_id: 'chan2' }));
    fireEvent.click(screen.getByTestId('channel-save'));
    await waitFor(() =>
      expect((screen.getByTestId('channel-test') as HTMLButtonElement).disabled).toBe(false),
    );
    expect(screen.queryByTestId('channel-dirty-line')).toBeNull();
  });

  it('treats a typed replacement token as unsaved', async () => {
    await mount(SET);
    fireEvent.click(screen.getByTestId('channel-token-replace'));
    type('channel-token-input', 'x');
    expect((screen.getByTestId('channel-test') as HTMLButtonElement).disabled).toBe(true);
  });

  it('drops a stale result when the form changes', async () => {
    await mount(SET);
    POST.mockResolvedValueOnce(ok({ ok: true, detail: 'connected as @orchestrator' }));
    fireEvent.click(screen.getByTestId('channel-test'));
    await screen.findByTestId('channel-test-status');

    type('channel-channel-id', 'chan2');
    expect(screen.queryByTestId('channel-test-status')).toBeNull();
  });
});
