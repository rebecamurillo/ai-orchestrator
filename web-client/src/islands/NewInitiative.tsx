/**
 * The New Initiative island (S7): the form, the pre-flight readout, the per-repository
 * table, the per-epic list and the decision bar, in one `client:load` island —
 * `new-initiative.astro`'s own precedent, `new.astro`/`NewWorkflow.tsx`'s structure and
 * idioms mirrored for a request shape with no per-Template catalog of its own.
 *
 * Pre-flight runs on load and 400 ms after the last field change, through `src/api/
 * client.ts` only (AD-1), guarded by `requestSeqRef` the same way `NewWorkflow.tsx` guards
 * its own poll: a superseded response must never land after a newer one.
 *
 * **`buildBody` gates the call itself**, not just the button. `InitiativeIn.project_id`/
 * `repository_id` are `format: uuid`, not nullable — unlike `PreflightIn`, there is no
 * partial shape `POST /initiatives/preflight` can be asked to answer, so an incomplete form
 * renders the empty pre-flight locally and never calls the endpoint at all.
 *
 * *Start initiative* is disabled while a pre-flight is in flight or pending, not only when
 * the last one refused — `NewWorkflow.tsx`'s own reasoning: between a keystroke and the
 * response that answers it, `start_allowed` describes a form the Operator has already
 * changed.
 */
import { useEffect, useRef, useState } from 'react';

import type { components } from '../api/schema';
import { api } from '../api/client';
import HarnessList from '../components/HarnessList';
import InitiativeFields from '../components/initiative/InitiativeFields';
import PreflightLines from '../components/PreflightLines';
import RepoTable from '../components/initiative/RepoTable';
import EpicList from '../components/initiative/EpicList';
import { orderText } from '../lib/initiative/preflight';
import { buildBody, repositoriesFor, type FormState } from '../lib/initiative/form';
import '../styles/new-workflow.css';
import '../styles/new-initiative.css';

type ProjectRead = components['schemas']['ProjectRead'];
type HarnessOut = components['schemas']['HarnessOut'];
type InitiativePreflightOut = components['schemas']['InitiativePreflightOut'];
type ProbeResultOut = components['schemas']['ProbeResultOut'];

interface Props {
  projects: ProjectRead[];
  harnesses: HarnessOut[];
  initial: FormState;
}

const DEBOUNCE_MS = 400;
const GENERIC_FAILURE_DETAIL = 'the request failed';
const PREFLIGHT_FAILED_LINE = 'pre-flight could not be read from backend-api';
const INCOMPLETE_FORM_DETAIL =
  'project, hub repository, base branch and initiative folder are required before an initiative can start';

function emptyPreflight(): InitiativePreflightOut {
  return { slug: '', start_allowed: false, lines: [], repos: [], epics: [], order: [] };
}

export default function NewInitiative({ projects, harnesses, initial }: Props) {
  const [state, setState] = useState<FormState>(initial);
  const [preflight, setPreflight] = useState<InitiativePreflightOut>(emptyPreflight());
  const [preflightFailed, setPreflightFailed] = useState(false);
  const [pending, setPending] = useState(true);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | undefined>(undefined);
  const [probeResults, setProbeResults] = useState<Record<string, ProbeResultOut>>({});
  const [probeInFlight, setProbeInFlight] = useState(false);
  const requestSeqRef = useRef(0);
  const probeSeqRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const stateRef = useRef(state);
  stateRef.current = state;

  async function runPreflight(): Promise<void> {
    const seq = ++requestSeqRef.current;
    const body = buildBody(stateRef.current);
    if (!body) {
      if (seq === requestSeqRef.current) {
        setPreflight(emptyPreflight());
        setPreflightFailed(false);
        if (timerRef.current === undefined) setPending(false);
      }
      return;
    }
    try {
      const { data, error } = await api.POST('/initiatives/preflight', { body });
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
      // a further change scheduled its own re-run while this one was in flight — leaving
      // `pending` true keeps *Start initiative* off an outcome that no longer describes the
      // form, `NewWorkflow.tsx::runPreflight`'s own reasoning
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

  async function runReadiness(name: string): Promise<void> {
    await api.POST('/harnesses/{name}/readiness', { params: { path: { name } } });
    window.location.href = '/runs';
  }

  function update(next: FormState): void {
    setState(next);
    setStartError(undefined);
    setPending(true);
    schedulePreflight();
  }

  useEffect(() => {
    void runPreflight();
    return () => clearTimeout(timerRef.current);
    // fires once, on load; every field change re-fires it through `update()` instead
  }, []);

  async function dispatch(): Promise<void> {
    const body = buildBody(state);
    if (!body) {
      // never a silent no-op: the button can be live while a required field is still empty
      setStartError(INCOMPLETE_FORM_DETAIL);
      return;
    }
    setStarting(true);
    setStartError(undefined);
    try {
      const { data, error } = await api.POST('/initiatives', { body });
      if (error) {
        setStartError(error.detail ?? error.title ?? GENERIC_FAILURE_DETAIL);
        return;
      }
      if (!data) {
        setStartError(GENERIC_FAILURE_DETAIL);
        return;
      }
      window.location.assign(`/workflows/initiative/${data.slug}`);
    } catch {
      setStartError(GENERIC_FAILURE_DETAIL);
    } finally {
      setStarting(false);
    }
  }

  const repositories = repositoriesFor(projects, state.projectId);
  const models = probeResults[state.harness]?.models ?? [];
  const dispatchDisabled = starting || pending || probeInFlight || !preflight.start_allowed;

  return (
    <div className="newwf">
      <div className="newwf-columns">
        <form
          className="newwf-form"
          data-testid="newin-form"
          onSubmit={(event) => event.preventDefault()}
        >
          <InitiativeFields
            state={state}
            projects={projects}
            repositories={repositories}
            models={models}
            onChange={update}
          />
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
        </form>

        <div className="newwf-side">
          <section className="newwf-section">
            <h2 className="newwf-section-head">PRE-FLIGHT</h2>
            {preflightFailed ? (
              <p className="newwf-preflight-failed" data-testid="newin-preflight-failed">
                {PREFLIGHT_FAILED_LINE}
              </p>
            ) : (
              <PreflightLines lines={preflight.lines} />
            )}
          </section>

          <section className="newwf-section">
            <h2 className="newwf-section-head">REPOSITORIES</h2>
            <RepoTable repos={preflight.repos} />
          </section>

          <section className="newwf-section">
            <h2 className="newwf-section-head">EPICS</h2>
            <EpicList epics={preflight.epics} order={preflight.order} />
            <p className="newin-order" data-testid="newin-order">
              order: {orderText(preflight.order)}
            </p>
          </section>
        </div>
      </div>

      <div className="newwf-bar">
        {startError ? (
          <p className="newwf-bar-error" data-testid="newin-start-error">
            {startError}
          </p>
        ) : null}
        <div className="newwf-bar-controls">
          <button
            type="button"
            className="newwf-start"
            data-testid="newin-dispatch"
            disabled={dispatchDisabled}
            onClick={() => void dispatch()}
          >
            Start initiative
          </button>
          <a className="newwf-cancel" data-testid="newin-cancel" href="/">
            Cancel
          </a>
        </div>
      </div>
    </div>
  );
}
