/**
 * The senior session's start form (story 2-4, CAP-7): scope, harness, and — once that
 * harness has been probed — its model. Fully controlled: `SessionPanel` owns the state and
 * the two reads (`GET /harnesses`, `GET /harnesses/{name}/probe`), so the static render of
 * each state is the state.
 *
 * The model control is the New Workflow form's own `ModelField`: a select over the probe's
 * models, or a text field when the harness lists none.
 */
import ModelField from '../ModelField';
import {
  DISMISS_LABEL,
  HARNESS_DEFAULT_LABEL,
  NO_HARNESS_LINE,
  OFFER_LINE,
  SCOPE_LABELS,
  START_LABEL,
  canStart,
  type HarnessOut,
  type ProbeResultOut,
  type SessionScope,
} from '../../lib/run/session';

interface Props {
  scopes: readonly SessionScope[];
  scope: SessionScope | '';
  /** The enabled harnesses; `null` while the list loads. */
  harnesses: readonly HarnessOut[] | null;
  harness: string;
  probe: ProbeResultOut | null;
  probing: boolean;
  model: string;
  posting: boolean;
  onScope: (scope: SessionScope) => void;
  onHarness: (name: string) => void;
  onModel: (model: string) => void;
  onStart: () => void;
  onDismiss: () => void;
}

export default function SessionStart({
  scopes,
  scope,
  harnesses,
  harness,
  probe,
  probing,
  model,
  posting,
  onScope,
  onHarness,
  onModel,
  onStart,
  onDismiss,
}: Props) {
  return (
    <div className="wf-session-form" data-testid="wf-session-form">
      <p className="wf-answer-hint">{OFFER_LINE}</p>
      <label className="wf-session-field">
        <span className="wf-session-label">SCOPE</span>
        <select
          data-testid="wf-session-scope"
          value={scope}
          onChange={(event) => onScope(event.target.value as SessionScope)}
        >
          {scopes.map((s) => (
            <option key={s} value={s}>
              {SCOPE_LABELS[s]}
            </option>
          ))}
        </select>
      </label>
      <label className="wf-session-field">
        <span className="wf-session-label">HARNESS</span>
        {harnesses === null ? (
          <span className="wf-session-note">loading harnesses</span>
        ) : harnesses.length === 0 ? (
          <span className="wf-session-note">{NO_HARNESS_LINE}</span>
        ) : (
          <select
            data-testid="wf-session-harness"
            value={harness}
            onChange={(event) => onHarness(event.target.value)}
          >
            <option value="">—</option>
            {harnesses.map((h) => (
              <option key={h.name} value={h.name}>
                {h.name}
              </option>
            ))}
          </select>
        )}
      </label>
      {probing ? <p className="wf-session-note">probing {harness}</p> : null}
      {probe && !probe.ok ? (
        <p className="wf-signal-error" data-testid="wf-session-probe-error">
          {probe.failing_reason ?? `${harness} failed its probe`}
        </p>
      ) : null}
      {probe?.ok ? (
        <label className="wf-session-field">
          <span className="wf-session-label">MODEL (optional)</span>
          <ModelField
            testId="wf-session-model"
            value={model}
            models={probe.models}
            placeholder={HARNESS_DEFAULT_LABEL}
            blankLabel={HARNESS_DEFAULT_LABEL}
            onChange={onModel}
          />
        </label>
      ) : null}
      <div className="wf-session-actions">
        <button
          type="button"
          className="wf-signal"
          data-testid="wf-session-start"
          disabled={!canStart({ scope, harness, probe, probing, posting })}
          onClick={onStart}
        >
          {START_LABEL}
        </button>
        <button
          type="button"
          className="wf-signal"
          data-testid="wf-session-dismiss"
          disabled={posting}
          onClick={onDismiss}
        >
          {DISMISS_LABEL}
        </button>
      </div>
    </div>
  );
}
