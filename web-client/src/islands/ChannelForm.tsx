/**
 * The Project's chat channel (story 3-5): read, save and probe through `src/api/client.ts`,
 * the island's only fetch caller (AD-1). The bot token exists in component state only
 * between typing and a successful save, and is sent only when the Operator typed one.
 */
import { useCallback, useEffect, useState } from 'react';

import { api } from '../api/client';
import {
  SLACK_NOTE,
  bodyFromForm,
  chooseProvider,
  errorsAfterEdit,
  errorsByField,
  formFromChannel,
  guarded,
  isDirty,
  type ChannelField,
  type ChannelFormState,
  type ChannelProvider,
  type FieldErrors,
} from '../lib/projects/channel';

interface Props {
  projectId: string;
}

type Load = { status: 'loading' } | { status: 'failed'; detail: string } | { status: 'ready' };
type Probe = { ok: boolean; detail: string };

const NOTE = 'the bot token is stored encrypted, never shown, and never given to an agent';
const NO_ERRORS: FieldErrors = { fields: {}, detail: null };

export default function ChannelForm({ projectId }: Props) {
  const [load, setLoad] = useState<Load>({ status: 'loading' });
  const [saved, setSaved] = useState<ChannelFormState | null>(null);
  const [form, setForm] = useState<ChannelFormState | null>(null);
  const [errors, setErrors] = useState<FieldErrors>(NO_ERRORS);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [probe, setProbe] = useState<Probe | null>(null);
  const [busy, setBusy] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const path = { params: { path: { project_id: projectId } } };

  const read = useCallback(async () => {
    setLoad({ status: 'loading' });
    const result = await guarded(() =>
      api.GET('/projects/{project_id}/channel', { params: { path: { project_id: projectId } } }),
    );
    if (result.data) {
      const loaded = formFromChannel(result.data);
      setSaved(loaded);
      setForm(loaded);
      setLoad({ status: 'ready' });
    } else {
      setLoad({ status: 'failed', detail: errorsByField(result.error).detail ?? '' });
    }
  }, [projectId]);

  useEffect(() => {
    void read();
  }, [read]);

  if (load.status === 'loading') return <p className="channel-form secondary-line">loading</p>;
  if (load.status === 'failed' || !form || !saved) {
    return (
      <section className="channel-form" data-testid="channel-form">
        <p className="field-error" data-testid="channel-load-error">
          {load.status === 'failed' ? load.detail : ''}
        </p>
        <button type="button" className="control" data-testid="channel-retry" onClick={read}>
          retry
        </button>
      </section>
    );
  }

  const dirty = isDirty(form, saved);
  const off = form.provider === 'off';
  const revealToken = form.replacingToken || !form.tokenSet;

  function edit(patch: Partial<ChannelFormState>) {
    setForm((current) => (current ? { ...current, ...patch } : current));
    setErrors((current) => errorsAfterEdit(current, patch));
    if (patch.allowedUsers !== undefined) setUsersError(null);
    setProbe(null);
    setJustSaved(false);
  }

  async function save() {
    if (!form) return;
    const built = bodyFromForm(form);
    setUsersError(built.ok ? null : built.error);
    setErrors(NO_ERRORS);
    if (!built.ok) return;
    setBusy(true);
    const result = await guarded(() =>
      api.PUT('/projects/{project_id}/channel', { ...path, body: built.body }),
    );
    setBusy(false);
    if (result.data) {
      const next = formFromChannel(result.data);
      setSaved(next);
      setForm(next);
      setProbe(null);
      setJustSaved(true);
    } else {
      setErrors(errorsByField(result.error));
    }
  }

  async function test() {
    setBusy(true);
    const result = await guarded(() => api.POST('/projects/{project_id}/channel/test', path));
    setBusy(false);
    if (result.data) setProbe(result.data);
    else setProbe({ ok: false, detail: errorsByField(result.error).detail ?? '' });
  }

  function fieldError(name: ChannelField, id: string) {
    const reason =
      name === 'allowed_users' ? (usersError ?? errors.fields[name]) : errors.fields[name];
    return reason ? (
      <p className="field-error" data-testid={`channel-${id}-error`}>
        {reason}
      </p>
    ) : null;
  }

  return (
    <section className="channel-form" data-testid="channel-form">
      <h3 className="channel-title">CHANNEL</h3>
      <p className="secondary-line" data-testid="channel-note">
        {NOTE}
      </p>

      <label className="field">
        <span className="field-label">PROVIDER</span>
        <select
          value={form.provider}
          disabled={busy}
          data-testid="channel-provider"
          onChange={(event) => edit(chooseProvider(form, event.target.value as ChannelProvider))}
        >
          <option value="off">off</option>
          <option value="mattermost">mattermost</option>
          <option value="slack">slack</option>
        </select>
      </label>

      {off ? null : (
        <>
          <label className="field">
            <span className="field-label">BASE URL</span>
            <input
              type="text"
              value={form.baseUrl}
              disabled={busy}
              data-testid="channel-base-url"
              onChange={(event) => edit({ baseUrl: event.target.value })}
            />
            {fieldError('base_url', 'base-url')}
          </label>

          <label className="field">
            <span className="field-label">CHANNEL ID</span>
            <input
              type="text"
              value={form.channelId}
              disabled={busy}
              data-testid="channel-channel-id"
              onChange={(event) => edit({ channelId: event.target.value })}
            />
            {fieldError('channel_id', 'channel-id')}
          </label>

          <div className="field">
            <span className="field-label">BOT TOKEN</span>
            {revealToken ? (
              <span className="masked-value">
                <input
                  type="password"
                  autoComplete="new-password"
                  value={form.token}
                  disabled={busy}
                  data-testid="channel-token-input"
                  onChange={(event) => edit({ token: event.target.value })}
                />
                {form.tokenSet ? (
                  <button
                    type="button"
                    className="control"
                    disabled={busy}
                    data-testid="channel-token-cancel"
                    onClick={() => edit({ replacingToken: false, token: '' })}
                  >
                    cancel
                  </button>
                ) : null}
              </span>
            ) : (
              <span className="masked-value" data-testid="channel-token-state">
                set
                <button
                  type="button"
                  className="control"
                  disabled={busy}
                  data-testid="channel-token-replace"
                  onClick={() => edit({ replacingToken: true })}
                >
                  replace
                </button>
              </span>
            )}
            {fieldError('token', 'token')}
          </div>

          <label className="field">
            <span className="field-label">ALLOWED USERS (one `id handle` per line)</span>
            <textarea
              value={form.allowedUsers}
              disabled={busy}
              data-testid="channel-allowed-users"
              onChange={(event) => edit({ allowedUsers: event.target.value })}
            />
            {fieldError('allowed_users', 'allowed-users')}
          </label>

          <label className="switch-label">
            <input
              type="checkbox"
              checked={form.metadataOnly}
              disabled={busy}
              data-testid="channel-metadata-only"
              onChange={(event) => edit({ metadataOnly: event.target.checked })}
            />
            <span>metadata only</span>
          </label>
          {form.provider === 'slack' ? (
            <p className="secondary-line" data-testid="channel-slack-note">
              {SLACK_NOTE}
            </p>
          ) : null}
        </>
      )}

      {errors.detail ? (
        <p className="field-error" data-testid="channel-error">
          {errors.detail}
        </p>
      ) : null}

      <div className="actions">
        <button
          type="button"
          className="control"
          disabled={busy}
          data-testid="channel-save"
          onClick={save}
        >
          save
        </button>
        <button
          type="button"
          className="control"
          disabled={busy || dirty || saved.provider === 'off'}
          data-testid="channel-test"
          onClick={test}
        >
          test
        </button>
        {dirty ? (
          <span className="secondary-line" data-testid="channel-dirty-line">
            save before testing
          </span>
        ) : null}
        {justSaved ? (
          <span className="secondary-line" data-testid="channel-saved">
            saved
          </span>
        ) : null}
        {probe ? (
          <span data-testid="channel-test-result">
            <span className="status-word" data-testid="channel-test-status">
              {probe.ok ? 'ok' : 'failed'}
            </span>{' '}
            <span className="secondary-line" data-testid="channel-test-detail">
              {probe.detail}
            </span>
          </span>
        ) : null}
      </div>
    </section>
  );
}
