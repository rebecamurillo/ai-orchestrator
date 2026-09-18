/**
 * The New Workflow island (4.13, SPEC CAP-13, UX-DR8): the form, the pre-flight readout, the
 * plan table and the decision bar, in one `client:load` island — `new.astro` mounts it once
 * its server-side reads found at least one Template to bind.
 *
 * Pre-flight runs on load and 400 ms after the last field change (Binding rules), through
 * `src/api/client.ts` only (AD-1) — never a `fetch` of its own. `requestSeqRef` is
 * `TemplateEditor.tsx`'s own guard against a superseded response landing after a newer one
 * (3.5, Review Triage Log finding 3): every call captures the counter it incremented to and
 * only applies its outcome while that value is still current.
 *
 * *Start run* is disabled while a pre-flight is in flight or pending, not only when the last
 * one refused: between a keystroke and the response that answers it, `start_allowed` describes
 * a form the Operator has already changed, and starting on that authorisation would start a
 * Run pre-flight never actually cleared.
 *
 * The URL carries the form state as query parameters (`src/lib/newwf/query.ts`) so a reload
 * restores it; `history.replaceState` keeps the address bar in sync without adding a history
 * entry per keystroke.
 */
import { useEffect, useRef, useState } from 'react';

import type { components } from '../api/schema';
import { api } from '../api/client';
import HarnessList from '../components/HarnessList';
import NewWorkflowFields from '../components/NewWorkflowFields';
import PlanTable from '../components/PlanTable';
import PreflightLines from '../components/PreflightLines';
import { formStateToQuery } from '../lib/newwf/query';
import {
  CONSENT_CHECK_TEXT,
  SAVE_TEXT,
  cloneCheckNote,
  preflightBody,
  repositoriesFor,
  repositoryById,
  runBody,
  usesHarness,
  type FormState,
  type ProbeResultOut,
} from '../lib/newwf/state';
import '../styles/new-workflow.css';

type ProjectRead = components['schemas']['ProjectRead'];
type TemplateSummary = components['schemas']['TemplateSummaryOut'];
type HarnessOut = components['schemas']['HarnessOut'];
type PreflightOut = components['schemas']['PreflightOut'];

interface Props {
  templates: TemplateSummary[];
  projects: ProjectRead[];
  harnesses: HarnessOut[];
  initial: FormState;
}

const DEBOUNCE_MS = 400;
const GENERIC_FAILURE_DETAIL = 'the request failed';
const PREFLIGHT_FAILED_LINE = 'pre-flight could not be read from backend-api';
const INCOMPLETE_FORM_DETAIL =
  'every field but model and manual estimate is required before a run can start';

function emptyPreflight(): PreflightOut {
  return {
    lines: [],
    start_allowed: false,
    queue_note: '',
    rows: null,
    plan_error: null,
    conflict_consent_required: false,
  };
}

export default function NewWorkflow({ templates, projects, harnesses, initial }: Props) {
  const [state, setState] = useState<FormState>(initial);
  const [preflight, setPreflight] = useState<PreflightOut>(emptyPreflight());
  const [preflightFailed, setPreflightFailed] = useState(false);
  const [pending, setPending] = useState(true);
  const [starting, setStarting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [startError, setStartError] = useState<string | undefined>(undefined);
  const [probeResults, setProbeResults] = useState<Record<string, ProbeResultOut>>({});
  const [probeInFlight, setProbeInFlight] = useState(false);
  const [conflictConsent, setConflictConsent] = useState(false);
  const requestSeqRef = useRef(0);
  const probeSeqRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const stateRef = useRef(state);
  stateRef.current = state;

  async function runPreflight(): Promise<void> {
    const seq = ++requestSeqRef.current;
    const body = preflightBody(stateRef.current, templates);
    try {
      const { data, error } = await api.POST('/runs/preflight', { body });
      if (seq !== requestSeqRef.current) return;
      if (error || !data) {
        setPreflight(emptyPreflight());
        setPreflightFailed(true);
        return;
      }
      setPreflight(data);
      setPreflightFailed(false);
    } catch {
      if (seq === requestSeqRef.current) {
        setPreflight(emptyPreflight());
        setPreflightFailed(true);
      }
    } finally {
      // `timerRef.current` still set means a further change was made while this request was
      // in flight and its own re-run is already scheduled: the form is dirty again, so
      // clearing `pending` here would flash *Start run* live against an outcome that no
      // longer describes the form
      if (seq === requestSeqRef.current && timerRef.current === undefined) setPending(false);
    }
  }

  function schedulePreflight(): void {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = undefined;
      void runPreflight();
    }, DEBOUNCE_MS);
  }

  async function runReadiness(name: string): Promise<void> {
    await api.POST('/harnesses/{name}/readiness', { params: { path: { name } } });
    window.location.href = '/runs';
  }

  async function runProbe(name: string): Promise<void> {
    const seq = ++probeSeqRef.current;
    setProbeInFlight(true);
    try {
      const { data } = await api.GET('/harnesses/{name}/probe', { params: { path: { name } } });
      if (seq !== probeSeqRef.current) return;
      if (data) {
        setProbeResults((prev) => ({ ...prev, [name]: data }));
        if (!data.ok) {
          setState((prev) => (prev.harness === name ? { ...prev, harness: '', model: '' } : prev));
        } else {
          setState((prev) =>
            prev.harness === name && data.models.length > 0 && !data.models.includes(prev.model)
              ? { ...prev, model: '' }
              : prev,
          );
        }
      }
    } finally {
      if (seq === probeSeqRef.current) setProbeInFlight(false);
    }
  }

  function update(next: FormState): void {
    setState(next);
    setStartError(undefined);
    setConflictConsent(false);
    // the last outcome describes a form that no longer exists; nothing may start on it
    setPending(true);
    const query = formStateToQuery(next).toString();
    const url = query ? `${window.location.pathname}?${query}` : window.location.pathname;
    window.history.replaceState(null, '', url);
    schedulePreflight();
  }

  useEffect(() => {
    void runPreflight();
    return () => clearTimeout(timerRef.current);
    // fires once, on load, exactly as the binding rules ask; every field change re-fires it
    // through `update()` instead
  }, []);

  async function startRun(): Promise<void> {
    const body = runBody(state, templates);
    if (!body) {
      // never a silent no-op: the button can be live while a required field is still empty
      setStartError(INCOMPLETE_FORM_DETAIL);
      return;
    }
    setStarting(true);
    setStartError(undefined);
    try {
      if (state.harness) {
        const { data: probe } = await api.GET('/harnesses/{name}/probe', {
          params: { path: { name: state.harness } },
        });
        if (probe && !probe.ok) {
          setProbeResults((prev) => ({ ...prev, [state.harness]: probe }));
          setPreflight({
            lines: [
              {
                check: 'HARNESS',
                status: 'fail',
                text: probe.failing_reason ?? 'probe failed',
                fix: null,
              },
            ],
            start_allowed: false,
            queue_note: '',
            rows: null,
            plan_error: null,
            conflict_consent_required: false,
          });
          return;
        }
      }
      const { data, error } = await api.POST('/runs', {
        body: { ...body, conflict_consent: conflictConsent, save: false },
      });
      if (error) {
        setStartError(error.detail ?? error.title ?? GENERIC_FAILURE_DETAIL);
        return;
      }
      if (!data) {
        setStartError(GENERIC_FAILURE_DETAIL);
        return;
      }
      window.location.assign(`/workflows/${data.run.id}`);
    } catch {
      setStartError(GENERIC_FAILURE_DETAIL);
    } finally {
      setStarting(false);
    }
  }

  const repositories = repositoriesFor(projects, state.projectId);
  const note = cloneCheckNote(repositoryById(repositories, state.repositoryId));
  const startDisabled =
    starting ||
    saving ||
    pending ||
    probeInFlight ||
    !preflight.start_allowed ||
    (preflight.conflict_consent_required && !conflictConsent);
  const saveDisabled = saving || starting || pending;

  async function saveRun(): Promise<void> {
    const body = runBody(state, templates);
    if (!body) {
      setStartError(INCOMPLETE_FORM_DETAIL);
      return;
    }
    setSaving(true);
    setStartError(undefined);
    try {
      const { data, error } = await api.POST('/runs', {
        body: { ...body, conflict_consent: conflictConsent, save: true },
      });
      if (error) {
        setStartError(error.detail ?? error.title ?? GENERIC_FAILURE_DETAIL);
        return;
      }
      if (!data) {
        setStartError(GENERIC_FAILURE_DETAIL);
        return;
      }
      window.location.assign(`/workflows/${data.run.id}`);
    } catch {
      setStartError(GENERIC_FAILURE_DETAIL);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="newwf">
      <div className="newwf-columns">
        <form
          className="newwf-form"
          data-testid="newwf-form"
          onSubmit={(event) => event.preventDefault()}
        >
          <NewWorkflowFields
            state={state}
            projects={projects}
            repositories={repositories}
            models={probeResults[state.harness]?.models ?? []}
            note={note}
            onChange={update}
          />
          {usesHarness(state.template) ? (
            <HarnessList
              harnesses={harnesses}
              selected={state.harness}
              probeResults={probeResults}
              onSelect={(name) => {
                update({ ...stateRef.current, harness: name, model: '' });
                void runProbe(name);
              }}
              onRunReadiness={runReadiness}
            />
          ) : null}
        </form>

        <div className="newwf-side">
          <section className="newwf-section">
            <h2 className="newwf-section-head">PRE-FLIGHT</h2>
            {preflightFailed ? (
              <p className="newwf-preflight-failed" data-testid="newwf-preflight-failed">
                {PREFLIGHT_FAILED_LINE}
              </p>
            ) : (
              <PreflightLines lines={preflight.lines} />
            )}
          </section>
          <section className="newwf-section">
            <h2 className="newwf-section-head">WHAT WILL RUN</h2>
            <PlanTable rows={preflight.rows} planError={preflight.plan_error} />
          </section>
        </div>
      </div>

      <div className="newwf-bar">
        {startError ? (
          <p className="newwf-bar-error" data-testid="newwf-start-error">
            {startError}
          </p>
        ) : null}
        {preflight.conflict_consent_required ? (
          <div className="newwf-consent" data-testid="newwf-consent">
            <label>
              <input
                type="checkbox"
                checked={conflictConsent}
                onChange={(e) => setConflictConsent(e.target.checked)}
                data-testid="newwf-consent-checkbox"
              />
              {CONSENT_CHECK_TEXT}
            </label>
          </div>
        ) : null}
        <div className="newwf-bar-controls">
          <button
            type="button"
            className="newwf-start"
            data-testid="newwf-start"
            disabled={startDisabled}
            onClick={() => void startRun()}
          >
            Start run
          </button>
          <button
            type="button"
            className="newwf-save"
            data-testid="newwf-save"
            disabled={saveDisabled}
            onClick={() => void saveRun()}
          >
            {SAVE_TEXT}
          </button>
          <a className="newwf-cancel" data-testid="newwf-cancel" href="/">
            Cancel
          </a>
          <span className="newwf-note" data-testid="newwf-note">
            {preflight.queue_note}
          </span>
        </div>
      </div>
    </div>
  );
}
