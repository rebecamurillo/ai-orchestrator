/**
 * `src/lib/projects/channel.ts` (story 3-5): the pure half of the Project channel form.
 * Matrix rows owned here: Load (off, set), Save new, Save keep, Turn off, Allowed users,
 * Dirty, and the error mapping behind every refusal the API can answer.
 */
import { describe, expect, it } from 'vitest';

import type { components } from '../../src/api/schema';
import {
  bodyFromForm,
  errorsByField,
  formFromChannel,
  formatAllowedUsers,
  isDirty,
  parseAllowedUsers,
  type ChannelFormState,
} from '../../src/lib/projects/channel';

type ChannelOut = components['schemas']['ChannelOut'];

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
  metadata_only: true,
};

function form(over: Partial<ChannelFormState> = {}): ChannelFormState {
  return { ...formFromChannel(SET), ...over };
}

describe('formFromChannel', () => {
  it('reads an off channel as empty fields with no token', () => {
    expect(formFromChannel(OFF)).toEqual({
      provider: 'off',
      baseUrl: '',
      channelId: '',
      allowedUsers: '',
      metadataOnly: false,
      tokenSet: false,
      replacingToken: false,
      token: '',
    });
  });

  it('fills the fields of a set channel and never carries a token', () => {
    expect(formFromChannel(SET)).toEqual({
      provider: 'mattermost',
      baseUrl: 'https://chat.example.com',
      channelId: 'chan1',
      allowedUsers: 'u1 alice\nu2 bob',
      metadataOnly: true,
      tokenSet: true,
      replacingToken: false,
      token: '',
    });
  });
});

describe('parseAllowedUsers and formatAllowedUsers', () => {
  it('parses one `id handle` per line', () => {
    expect(parseAllowedUsers('u1 alice\nu2 bob')).toEqual({
      ok: true,
      users: [
        { id: 'u1', handle: 'alice' },
        { id: 'u2', handle: 'bob' },
      ],
    });
  });

  it('skips blank lines, trims, and accepts any run of whitespace between the fields', () => {
    expect(parseAllowedUsers('\n  u1 \t alice  \r\n\n')).toEqual({
      ok: true,
      users: [{ id: 'u1', handle: 'alice' }],
    });
  });

  it('reads empty text as no users', () => {
    expect(parseAllowedUsers('')).toEqual({ ok: true, users: [] });
  });

  it('refuses a line with one field, naming the line', () => {
    expect(parseAllowedUsers('u1 alice\nu2')).toEqual({
      ok: false,
      error: 'line 2: expected `id handle`, two fields',
    });
  });

  it('refuses a line with three fields, naming the line', () => {
    expect(parseAllowedUsers('u1 alice extra')).toEqual({
      ok: false,
      error: 'line 1: expected `id handle`, two fields',
    });
  });

  it('numbers lines by position, blank lines included', () => {
    expect(parseAllowedUsers('\n\nu1')).toEqual({
      ok: false,
      error: 'line 3: expected `id handle`, two fields',
    });
  });

  it('formats users back to the text the parser reads', () => {
    const users = [
      { id: 'u1', handle: 'alice' },
      { id: 'u2', handle: 'bob' },
    ];
    expect(formatAllowedUsers(users)).toBe('u1 alice\nu2 bob');
    expect(formatAllowedUsers([])).toBe('');
    expect(parseAllowedUsers(formatAllowedUsers(users))).toEqual({ ok: true, users });
  });
});

describe('bodyFromForm', () => {
  it('sends the token when the Operator typed a replacement', () => {
    expect(bodyFromForm(form({ replacingToken: true, token: 'secret-1' }))).toEqual({
      ok: true,
      body: {
        provider: 'mattermost',
        base_url: 'https://chat.example.com',
        channel_id: 'chan1',
        allowed_users: [
          { id: 'u1', handle: 'alice' },
          { id: 'u2', handle: 'bob' },
        ],
        metadata_only: true,
        token: 'secret-1',
      },
    });
  });

  it('sends a first token typed for a channel that has none', () => {
    const result = bodyFromForm(form({ tokenSet: false, token: 'first' }));
    expect(result.ok && result.body.token).toBe('first');
  });

  it('has no token key when the stored token was kept', () => {
    const result = bodyFromForm(form());
    expect(result.ok).toBe(true);
    expect(result.ok && 'token' in result.body).toBe(false);
  });

  it('has no token key when replace was pressed and nothing was typed', () => {
    const result = bodyFromForm(form({ replacingToken: true, token: '' }));
    expect(result.ok && 'token' in result.body).toBe(false);
  });

  it('has no token key when text is left in a token field that is not being replaced', () => {
    const result = bodyFromForm(form({ replacingToken: false, token: 'stale' }));
    expect(result.ok && 'token' in result.body).toBe(false);
  });

  it('sends only the provider for off', () => {
    expect(bodyFromForm(form({ provider: 'off', token: 'x', replacingToken: true }))).toEqual({
      ok: true,
      body: { provider: 'off' },
    });
  });

  it('trims the text fields', () => {
    const result = bodyFromForm(form({ baseUrl: ' https://h ', channelId: ' c ' }));
    expect(result.ok && [result.body.base_url, result.body.channel_id]).toEqual(['https://h', 'c']);
  });

  it('refuses a malformed allowed-users line without a body', () => {
    expect(bodyFromForm(form({ allowedUsers: 'u1' }))).toEqual({
      ok: false,
      error: 'line 1: expected `id handle`, two fields',
    });
  });
});

describe('isDirty', () => {
  const saved = formFromChannel(SET);

  it('is clean for the form just loaded', () => {
    expect(isDirty(formFromChannel(SET), saved)).toBe(false);
  });

  it.each([
    ['provider', { provider: 'off' as const }],
    ['base url', { baseUrl: 'https://other' }],
    ['channel id', { channelId: 'chan2' }],
    ['allowed users', { allowedUsers: 'u1 alice' }],
    ['metadata only', { metadataOnly: false }],
    ['a typed token', { replacingToken: true, token: 'x' }],
  ])('is dirty after %s changes', (_name, change) => {
    expect(isDirty({ ...saved, ...change }, saved)).toBe(true);
  });

  it('stays clean when replace was pressed and nothing typed', () => {
    expect(isDirty({ ...saved, replacingToken: true }, saved)).toBe(false);
  });

  it('ignores whitespace around the text fields', () => {
    expect(isDirty({ ...saved, baseUrl: ` ${saved.baseUrl} ` }, saved)).toBe(false);
  });
});

describe('errorsByField', () => {
  it('puts each errors[].path at its field, dropping the body prefix', () => {
    expect(
      errorsByField({
        title: 'validation failed',
        status: 422,
        detail: 'body.base_url: a base URL is http(s)://host, with no whitespace',
        errors: [
          { path: 'body.base_url', reason: 'a base URL is http(s)://host, with no whitespace' },
          { path: 'body.token', reason: 'a token is printable ASCII with no whitespace' },
        ],
      }),
    ).toEqual({
      fields: {
        base_url: 'a base URL is http(s)://host, with no whitespace',
        token: 'a token is printable ASCII with no whitespace',
      },
      detail: null,
    });
  });

  it('maps an allowed_users entry to the allowed users field', () => {
    const result = errorsByField({
      title: 'validation failed',
      status: 422,
      errors: [{ path: 'body.allowed_users.1.handle', reason: 'a handle is non-empty' }],
    });
    expect(result.fields).toEqual({ allowed_users: 'a handle is non-empty' });
  });

  it('keeps the first reason when one field has several', () => {
    const result = errorsByField({
      title: 'validation failed',
      status: 422,
      errors: [
        { path: 'body.channel_id', reason: 'first' },
        { path: 'body.channel_id', reason: 'second' },
      ],
    });
    expect(result.fields).toEqual({ channel_id: 'first' });
  });

  it('shows an error with an unknown or missing path as the general detail', () => {
    const result = errorsByField({
      title: 'validation failed',
      status: 422,
      errors: [{ path: 'body', reason: 'whole body refused' }, { reason: 'no path' }],
    });
    expect(result).toEqual({ fields: {}, detail: 'whole body refused; no path' });
  });

  it('shows the detail of a refusal that names no field, verbatim', () => {
    expect(
      errorsByField({
        title: 'invalid',
        status: 422,
        detail: 'token: enter the token again when the host changes',
      }),
    ).toEqual({
      fields: {},
      detail: 'token: enter the token again when the host changes',
    });
  });

  it('shows a 409 detail', () => {
    expect(
      errorsByField({
        title: 'conflict',
        status: 409,
        detail: 'the built-in Project is read-only',
      }),
    ).toEqual({ fields: {}, detail: 'the built-in Project is read-only' });
  });

  it('falls back to the title, then to a plain line, when there is no detail', () => {
    expect(errorsByField({ title: 'not found', status: 404 }).detail).toBe('not found');
    expect(errorsByField(undefined).detail).toBe('request failed');
    expect(errorsByField('<html>502</html>').detail).toBe('request failed');
  });

  it('treats an empty errors list as none', () => {
    expect(errorsByField({ title: 'bad', status: 422, detail: 'd', errors: [] })).toEqual({
      fields: {},
      detail: 'd',
    });
  });
});
