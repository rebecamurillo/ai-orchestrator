/**
 * The pure half of the Project channel form (story 3-5): form state from the API's
 * `ChannelOut`, the `PUT` body back out of it, the allowed-users text, and where each
 * refusal is shown. No fetch and no DOM, so every rule is unit-testable.
 */
import type { components } from '../../api/schema';

type ChannelOut = components['schemas']['ChannelOut'];
type ChannelIn = components['schemas']['ChannelIn'];
type ChatUser = components['schemas']['ChatUserIn'];
type ProblemDetail = components['schemas']['ProblemDetail'];

export type ChannelProvider = ChannelOut['provider'];

/** What the Operator sees. The token lives here only between typing and a save. */
export interface ChannelFormState {
  provider: ChannelProvider;
  baseUrl: string;
  channelId: string;
  allowedUsers: string;
  metadataOnly: boolean;
  tokenSet: boolean;
  replacingToken: boolean;
  token: string;
}

export type ChannelField =
  'provider' | 'base_url' | 'channel_id' | 'token' | 'allowed_users' | 'metadata_only';

export type ParsedUsers = { ok: true; users: ChatUser[] } | { ok: false; error: string };
export type BuiltBody = { ok: true; body: ChannelIn } | { ok: false; error: string };

export interface FieldErrors {
  fields: Partial<Record<ChannelField, string>>;
  detail: string | null;
}

const FIELDS: readonly ChannelField[] = [
  'provider',
  'base_url',
  'channel_id',
  'token',
  'allowed_users',
  'metadata_only',
];

const REQUEST_FAILED = 'request failed';

export function formatAllowedUsers(users: readonly ChatUser[]): string {
  return users.map((user) => `${user.id} ${user.handle}`).join('\n');
}

export function formFromChannel(channel: ChannelOut): ChannelFormState {
  return {
    provider: channel.provider,
    baseUrl: channel.base_url ?? '',
    channelId: channel.channel_id ?? '',
    allowedUsers: formatAllowedUsers(channel.allowed_users),
    metadataOnly: channel.metadata_only,
    tokenSet: channel.token_set,
    replacingToken: false,
    token: '',
  };
}

/** One `id handle` per line; blank lines are skipped and the rest are numbered as typed. */
export function parseAllowedUsers(text: string): ParsedUsers {
  const users: ChatUser[] = [];
  const lines = text.split('\n');
  for (const [index, line] of lines.entries()) {
    const fields = line.trim().split(/\s+/).filter(Boolean);
    if (fields.length === 0) continue;
    const [id, handle] = fields;
    if (fields.length !== 2 || id === undefined || handle === undefined) {
      return { ok: false, error: `line ${index + 1}: expected \`id handle\`, two fields` };
    }
    users.push({ id, handle });
  }
  return { ok: true, users };
}

/** The token is sent only when the Operator typed a replacement; otherwise the key is absent. */
export function bodyFromForm(form: ChannelFormState): BuiltBody {
  // The generated type marks the defaulted `metadata_only` required; `off` needs no other field.
  if (form.provider === 'off') return { ok: true, body: { provider: 'off' } as ChannelIn };
  const parsed = parseAllowedUsers(form.allowedUsers);
  if (!parsed.ok) return parsed;
  const body: ChannelIn = {
    provider: form.provider,
    base_url: form.baseUrl.trim(),
    channel_id: form.channelId.trim(),
    allowed_users: parsed.users,
    metadata_only: form.metadataOnly,
  };
  if (typedToken(form) !== '') body.token = form.token;
  return { ok: true, body };
}

function typedToken(form: ChannelFormState): string {
  return form.replacingToken || !form.tokenSet ? form.token : '';
}

/** Whether the form differs from the channel last saved, which is all Test can probe. */
export function isDirty(form: ChannelFormState, saved: ChannelFormState): boolean {
  return (
    form.provider !== saved.provider ||
    form.baseUrl.trim() !== saved.baseUrl.trim() ||
    form.channelId.trim() !== saved.channelId.trim() ||
    form.allowedUsers.trim() !== saved.allowedUsers.trim() ||
    form.metadataOnly !== saved.metadataOnly ||
    typedToken(form) !== ''
  );
}

function fieldOf(path: string | null | undefined): ChannelField | null {
  const key = (path ?? '').replace(/^body\./, '').split('.')[0];
  return FIELDS.find((field) => field === key) ?? null;
}

/**
 * Each `errors[].path` goes to its field; whatever names no field, and a refusal with no
 * `errors[]` at all (a 409, or a 422 whose reason leads with `token: `), comes back as the
 * one general `detail`, in the API's own words.
 */
export function errorsByField(
  problem: Partial<ProblemDetail> | string | null | undefined,
): FieldErrors {
  if (problem === null || typeof problem !== 'object')
    return { fields: {}, detail: REQUEST_FAILED };
  const fields: FieldErrors['fields'] = {};
  const loose: string[] = [];
  for (const error of problem.errors ?? []) {
    const field = fieldOf(error.path);
    if (field === null) loose.push(error.reason);
    else fields[field] ??= error.reason;
  }
  if (loose.length > 0) return { fields, detail: loose.join('; ') };
  if (Object.keys(fields).length > 0) return { fields, detail: null };
  return { fields, detail: problem.detail ?? problem.title ?? REQUEST_FAILED };
}

const EDIT_CLEARS: Partial<Record<keyof ChannelFormState, ChannelField>> = {
  baseUrl: 'base_url',
  channelId: 'channel_id',
  token: 'token',
  allowedUsers: 'allowed_users',
  metadataOnly: 'metadata_only',
};

/** Editing a field drops that field's refusal, and only that one. */
export function errorsAfterEdit(
  errors: FieldErrors,
  patch: Partial<ChannelFormState>,
): FieldErrors {
  const fields = { ...errors.fields };
  for (const key of Object.keys(patch) as (keyof ChannelFormState)[]) {
    const field = EDIT_CLEARS[key];
    if (field !== undefined) delete fields[field];
  }
  return { ...errors, fields };
}
