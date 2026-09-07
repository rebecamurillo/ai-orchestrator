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
 * The URL carries the form state as query parameters (`src/lib/newwf/query.ts`) so a reload
 * restores it; `history.replaceState` keeps the address bar in sync without adding a history
 * entry per keystroke.
 */
import { useEffect, useRef, useState } from 'react';

import type { components } from '../api/schema';
import { api } from '../api/client';
import PlanTable from '../components/PlanTable';
import PreflightLines from '../components/PreflightLines';
import { formStateToQuery } from '../lib/newwf/query';
import {
  TEMPLATE_INPUT_FIELDS,
  TEMPLATE_ORDER,
  cloneCheckNote,
  harnessLine,
  isTemplateName,
  preflightBody,
  repositoriesFor,
  repositoryById,
  runBody,
  withInput,
  withTemplate,
  type FormState,
  type TemplateName,
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

function emptyPreflight(): PreflightOut {
  return { lines: [], start_allowed: false, queue_note: '', rows: null, plan_error: null };
}

export default function NewWorkflow({ templates, projects, harnesses, initial }: Props) {
  const [state, setState] = useState<FormState>(initial);
  const [preflight, setPreflight] = useState<PreflightOut>(emptyPreflight());
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | undefined>(undefined);
  const requestSeqRef = useRef(0);
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
        return;
      }
      setPreflight(data);
    } catch {
      if (seq === requestSeqRef.current) setPreflight(emptyPreflight());
    }
  }

  function schedulePreflight(): void {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => void runPreflight(), DEBOUNCE_MS);
  }

  function update(next: FormState): void {
    setState(next);
    setStartError(undefined);
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
    if (!body) return;
    setStarting(true);
    setStartError(undefined);
    try {
      const { data, error } = await api.POST('/runs', { body });
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
  const selectedRepository = repositoryById(repositories, state.repositoryId);
  const note = cloneCheckNote(selectedRepository);
  const showHarnesses = state.template !== 'repo-init';
  const startDisabled = starting || !preflight.start_allowed;

  return (
    <div className="newwf">
      <div className="newwf-columns">
        <form
          className="newwf-form"
          data-testid="newwf-form"
          onSubmit={(event) => event.preventDefault()}
        >
          <label className="newwf-field">
            <span className="newwf-field-label">TEMPLATE</span>
            <select
              data-testid="newwf-template"
              value={state.template}
              onChange={(event) => {
                const value = event.target.value;
                if (isTemplateName(value)) update(withTemplate(state, value as TemplateName));
              }}
            >
              {TEMPLATE_ORDER.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>

          <label className="newwf-field">
            <span className="newwf-field-label">PROJECT</span>
            <select
              data-testid="newwf-project"
              value={state.projectId}
              onChange={(event) =>
                update({ ...state, projectId: event.target.value, repositoryId: '' })
              }
            >
              <option value="">—</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>

          <label className="newwf-field">
            <span className="newwf-field-label">REPOSITORY</span>
            <select
              data-testid="newwf-repository"
              value={state.repositoryId}
              onChange={(event) => {
                const repository = repositoryById(repositories, event.target.value);
                update({
                  ...state,
                  repositoryId: event.target.value,
                  baseBranch: state.baseBranch || repository?.default_branch || '',
                });
              }}
            >
              <option value="">—</option>
              {repositories.map((repository) => (
                <option key={repository.id} value={repository.id}>
                  {repository.slug}
                </option>
              ))}
            </select>
            {note ? <span className="newwf-field-note">{note}</span> : null}
          </label>

          <label className="newwf-field">
            <span className="newwf-field-label">BASE BRANCH</span>
            <input
              type="text"
              data-testid="newwf-base"
              value={state.baseBranch}
              onChange={(event) => update({ ...state, baseBranch: event.target.value })}
            />
          </label>

          {TEMPLATE_INPUT_FIELDS[state.template].map((field) => (
            <label className="newwf-field" key={field.key}>
              <span className="newwf-field-label">{field.label}</span>
              <input
                type="text"
                data-testid={`newwf-input-${field.key}`}
                value={state.inputs[field.key] ?? ''}
                onChange={(event) => update(withInput(state, field.key, event.target.value))}
              />
            </label>
          ))}

          {showHarnesses ? (
            <div className="newwf-field">
              <span className="newwf-field-label">HARNESS</span>
              <div className="newwf-harnesses">
                {harnesses.map((harness) => (
                  <label
                    className="newwf-harness"
                    key={harness.name}
                    data-testid={`newwf-harness-${harness.name}`}
                  >
                    <input
                      type="radio"
                      name="newwf-harness"
                      value={harness.name}
                      disabled={!harness.enabled}
                      checked={state.harness === harness.name}
                      onChange={() => update({ ...state, harness: harness.name })}
                    />
                    {harnessLine(harness)}
                  </label>
                ))}
              </div>
            </div>
          ) : null}

          <label className="newwf-field">
            <span className="newwf-field-label">MODEL</span>
            <input
              type="text"
              data-testid="newwf-model"
              placeholder="harness default"
              value={state.model}
              onChange={(event) => update({ ...state, model: event.target.value })}
            />
          </label>

          <label className="newwf-field">
            <span className="newwf-field-label">BUDGET (USD)</span>
            <input
              type="text"
              data-testid="newwf-budget"
              value={state.budgetUsd}
              onChange={(event) => update({ ...state, budgetUsd: event.target.value })}
            />
          </label>

          <label className="newwf-field newwf-switch">
            <input
              type="checkbox"
              data-testid="newwf-rereview"
              checked={state.reReviewDone}
              onChange={(event) => update({ ...state, reReviewDone: event.target.checked })}
            />
            <span>re-review done stories</span>
          </label>

          <label className="newwf-field">
            <span className="newwf-field-label">MANUAL ESTIMATE (H)</span>
            <input
              type="text"
              data-testid="newwf-estimate"
              value={state.manualEstimateH}
              onChange={(event) => update({ ...state, manualEstimateH: event.target.value })}
            />
          </label>
        </form>

        <div className="newwf-side">
          <PreflightLines lines={preflight.lines} />
          <PlanTable rows={preflight.rows} planError={preflight.plan_error} />
        </div>
      </div>

      <div className="newwf-bar">
        {startError ? (
          <p className="newwf-bar-error" data-testid="newwf-start-error">
            {startError}
          </p>
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
