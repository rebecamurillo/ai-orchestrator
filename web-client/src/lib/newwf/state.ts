/**
 * Pure state for the New Workflow form (4.13, UX-DR8) — no DOM, no fetch, so it unit-tests
 * without rendering (`web-client/AGENTS.md`).
 *
 * The Template list is not here: it comes from `newwf/catalog.ts`, and every function below
 * that needs it takes a `TemplateCatalog`. The `templates` prop is read only to look up
 * `latest_version` for the selected name.
 */
import type { components } from '../../api/schema';
import {
  fieldsFor,
  firstTemplate,
  offers,
  usesHarness as catalogUsesHarness,
  type TemplateCatalog,
} from './catalog';

type LineOut = components['schemas']['LineOut'];
type PreflightIn = components['schemas']['PreflightIn'];
type RunIn = components['schemas']['RunIn'];
type TemplateSummary = components['schemas']['TemplateSummaryOut'];
type RepositoryOut = components['schemas']['RepositoryOut'];
type HarnessOut = components['schemas']['HarnessOut'];
export type ProbeResultOut = components['schemas']['ProbeResultOut'];

/** The guard a `<select>`'s change event needs before its value becomes the Template. */
export function isTemplateName(value: string, catalog: TemplateCatalog): boolean {
  return offers(catalog, value);
}

export interface FormState {
  /** A Template name the catalog offers; `''` when it offers none at all. */
  template: string;
  projectId: string;
  repositoryId: string;
  baseBranch: string;
  /** Keyed by the current Template's declared input names; a field the new Template does not
   * declare is dropped rather than carried across a change. */
  inputs: Record<string, string>;
  harness: string;
  model: string;
  budgetUsd: string;
  reReviewDone: boolean;
  manualEstimateH: string;
}

/** The form as it opens: the catalog's first Template, fields seeded from its defaults. */
export function defaultFormState(catalog: TemplateCatalog): FormState {
  const template = firstTemplate(catalog);
  const inputs: Record<string, string> = {};
  for (const field of fieldsFor(catalog, template)) inputs[field.key] = field.initial;
  return {
    template,
    projectId: '',
    repositoryId: '',
    baseBranch: '',
    inputs,
    harness: '',
    model: '',
    budgetUsd: '',
    reReviewDone: false,
    manualEstimateH: '',
  };
}

/** Whether this Template dispatches a harness — by its declared inputs, never by name. */
export function usesHarness(template: string, catalog: TemplateCatalog): boolean {
  return catalogUsesHarness(catalog, template);
}

/**
 * Switching template keeps every field but the inputs the new template does not have, and
 * clears `harness` for a template whose form has no harness list: hiding the control while
 * still submitting its value would post a harness the Operator can no longer see or change.
 * A field the previous Template never held opens at the new one's declared default.
 */
export function withTemplate(
  state: FormState,
  template: string,
  catalog: TemplateCatalog,
): FormState {
  // an unoffered name would leave a form with no fields and no version to pin
  if (!offers(catalog, template)) return state;
  const inputs: Record<string, string> = {};
  for (const field of fieldsFor(catalog, template)) {
    inputs[field.key] = state.inputs[field.key] ?? field.initial;
  }
  return {
    ...state,
    template,
    inputs,
    harness: usesHarness(template, catalog) ? state.harness : '',
  };
}

export function withInput(state: FormState, key: string, value: string): FormState {
  return { ...state, inputs: { ...state.inputs, [key]: value } };
}

/**
 * The models this instance offers for one harness, from `GET /harnesses` (7.3).
 *
 * `[]` for a harness that publishes none — which is every harness but `local`, and is the
 * statement that it takes a free-text model name rather than a gap in the response. `models`
 * is optional in the generated type, so a backend that predates the field reads the same as a
 * harness that has none: the text field, exactly as before.
 */
export function modelsFor(harnesses: HarnessOut[], harness: string): string[] {
  return harnesses.find((candidate) => candidate.name === harness)?.models ?? [];
}

/**
 * Selecting a harness keeps a model only if the new harness still offers it.
 *
 * `local` turns the model field into a select over `LOCAL_MODELS`, and a select cannot show a
 * value that is not one of its options: a model typed for `claude` and carried into `local`
 * would leave the control blank while the form still submitted the old string. Clearing it is
 * the honest state — the field then reads "harness default", which is what an unset model is.
 *
 * A harness offering no models keeps whatever was typed, because there is nothing to check it
 * against and the Operator's own text is the value.
 */
export function withHarness(state: FormState, harness: string, harnesses: HarnessOut[]): FormState {
  const models = modelsFor(harnesses, harness);
  const keep = models.length === 0 || models.includes(state.model);
  return { ...state, harness, model: keep ? state.model : '' };
}

/** Every model-named input back at its declared default — the harness it was chosen for is gone. */
export function resetModelInputs(state: FormState, catalog: TemplateCatalog): FormState {
  const inputs = { ...state.inputs };
  for (const field of fieldsFor(catalog, state.template)) {
    if (field.modelChoice) inputs[field.key] = field.initial;
  }
  return { ...state, inputs };
}

/**
 * With a non-empty `models` list, a model-named input holding a value outside it is cleared:
 * a select cannot show it, and submitting it unseen is the failure this form exists to prevent.
 * An empty list means free text, so values stand. Returns `state` itself when nothing changes.
 */
export function reconcileModelInputs(
  state: FormState,
  models: string[],
  catalog: TemplateCatalog,
): FormState {
  if (models.length === 0) return state;
  let inputs: Record<string, string> | undefined;
  for (const field of fieldsFor(catalog, state.template)) {
    const value = state.inputs[field.key] ?? '';
    if (field.modelChoice && value !== '' && !models.includes(value)) {
      inputs ??= { ...state.inputs };
      inputs[field.key] = '';
    }
  }
  return inputs ? { ...state, inputs } : state;
}

/** The Repositories of the selected Project, or none while nothing is selected. */
export function repositoriesFor(
  projects: components['schemas']['ProjectRead'][],
  projectId: string,
): RepositoryOut[] {
  return projects.find((project) => project.id === projectId)?.repositories ?? [];
}

export function repositoryById(
  repositories: RepositoryOut[],
  repositoryId: string,
): RepositoryOut | undefined {
  return repositories.find((repository) => repository.id === repositoryId);
}

/** "clone check failed · new runs blocked" beside a Repository whose last check failed. */
export const CLONE_CHECK_FAILED_NOTE = 'clone check failed · new runs blocked';

export function cloneCheckNote(repository: RepositoryOut | undefined): string | undefined {
  return repository?.clone_check.status === 'failed' ? CLONE_CHECK_FAILED_NOTE : undefined;
}

/** `latest_version` for a Template name, from whatever `GET /templates` (plus the page's
 * own best-effort resolution of a deep-linked name) answered — `undefined` when unknown. */
export function latestVersion(templates: TemplateSummary[], name: string): number | undefined {
  return templates.find((template) => template.name === name)?.latest_version;
}

export function preflightBody(state: FormState, templates: TemplateSummary[]): PreflightIn {
  return {
    template_name: state.template,
    template_version: latestVersion(templates, state.template) ?? null,
    project_id: state.projectId || null,
    repository_id: state.repositoryId || null,
    base_branch: state.baseBranch || null,
    inputs: state.inputs,
    harness: state.harness || null,
    model: state.model || null,
    budget_usd: state.budgetUsd || null,
    re_review_done: state.reReviewDone,
  };
}

/** `null` when a field `POST /runs` requires is still unset — the caller's own guard against
 * calling it before `start_allowed` could ever be true.
 *
 * `conflict_consent` is intentionally excluded: it is non-persistent island-local state that
 * the island spreads on top of this body at call time (`NewWorkflow.tsx::startRun`). */
export function runBody(
  state: FormState,
  templates: TemplateSummary[],
): Omit<RunIn, 'conflict_consent' | 'save'> | null {
  const version = latestVersion(templates, state.template);
  if (!state.projectId || !state.repositoryId || !state.baseBranch) {
    return null;
  }
  if (version === undefined) return null;
  return {
    template_name: state.template,
    template_version: version,
    project_id: state.projectId,
    repository_id: state.repositoryId,
    base_branch: state.baseBranch,
    budget_usd: state.budgetUsd !== '' ? state.budgetUsd : null,
    inputs: state.inputs,
    harness: state.harness || null,
    model: state.model || null,
    manual_estimate_h: state.manualEstimateH || null,
    re_review_done: state.reReviewDone,
  };
}

/** The consent text shown when a concurrent run on the same repository is detected (story
 * 5-2). Shared between the island and the test so neither duplicates the string. */
export const CONSENT_CHECK_TEXT = 'this can lead to merge conflicts';

/** `ok / ! / x / —` — the brief's own words, never an icon. */
export function lineWord(status: LineOut['status']): string {
  switch (status) {
    case 'ok':
      return 'ok';
    case 'warn':
      return '!';
    case 'fail':
      return 'x';
    case 'skip':
      return '—';
  }
}

/** The test-id suffix for one check line: lower-kebab, and every character that is not a
 * letter, a digit or a dash folded to a dash, so `"SPEC.md"` becomes `spec-md` and the id is
 * a single token no CSS selector or `getByTestId` has to escape. */
export function checkSlug(check: string): string {
  return check
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/**
 * The part of the harness line before its `re-run readiness` link:
 * `{name} · enabled | disabled: {failing_check or "no readiness run"} · last readiness
 * {time or —} · `. The link itself is an anchor the component renders, not text — the brief
 * puts it in scope ("here the link points to it") even though Epic 5 provides the endpoint.
 */
export function harnessLineText(harness: HarnessOut): string {
  const status = harness.enabled
    ? 'enabled'
    : `disabled: ${harness.failing_check ?? 'no readiness run'}`;
  const readiness = harness.last_readiness_at ? readinessTime(harness.last_readiness_at) : '—';
  return `${harness.name} · ${status} · last readiness ${readiness} · `;
}

/**
 * The part of the harness line before its `re-run readiness` link, using a live probe result
 * instead of the SSR `enabled` flag.  Format mirrors `harnessLineText` but replaces the
 * `enabled | disabled: …` segment with either `"ok"` or the `failing_reason` string, and
 * always uses `harness.last_readiness_at` for the timestamp.
 */
export function harnessProbeLineText(harness: HarnessOut, result: ProbeResultOut): string {
  const status = result.ok ? 'ok' : (result.failing_reason ?? 'probe failed');
  const readiness = harness.last_readiness_at ? readinessTime(harness.last_readiness_at) : '—';
  return `${harness.name} · ${status} · last readiness ${readiness} · `;
}

/** The whole line as one string, link text included — what a reader sees, and what the
 * acceptance criterion quotes verbatim. */
export function harnessLine(harness: HarnessOut): string {
  return `${harnessLineText(harness)}${READINESS_LINK_LABEL}`;
}

export const READINESS_LINK_LABEL = 're-run readiness';

/** Where the `re-run readiness` link points (Epic 5 serves it; a 404 until then). */
export function readinessHref(name: string): string {
  return `/api/harnesses/${encodeURIComponent(name)}/readiness`;
}

/** Stated beside the link while `contracts/openapi.json` carries no readiness route — see
 * `src/components/HarnessList.tsx` for why this is a fact about the build, not a guess. */
export const READINESS_NOT_AVAILABLE = 'not available yet';

/** Text for the note span beside the "re-run readiness" link (story 2-4).
 *
 * Joins the non-empty parts of `readinessTime(last_readiness_at)` and `failing_check` with
 * ` · `.  Returns `""` when both are null — the island passes `onRunReadiness` and shows this
 * badge; the unit-test / SSR path does not pass the prop and shows `READINESS_NOT_AVAILABLE`
 * instead.
 */
export function readinessBadgeText(harness: HarnessOut): string {
  const parts: string[] = [];
  if (harness.last_readiness_at) {
    parts.push(readinessTime(harness.last_readiness_at));
  }
  if (harness.failing_check) {
    parts.push(harness.failing_check);
  }
  return parts.join(' · ');
}

function readinessTime(iso: string): string {
  return iso.slice(0, 19).replace('T', ' ');
}

/**
 * The form state a URL asked for, reconciled against what the page actually loaded: a
 * Repository that is not one of the named Project's, and a harness that is not enabled, are
 * both dropped. Without this a link can put a value into a `<select>` that has no matching
 * `<option>` (so the control reads `—` while the state still holds the id) or check a
 * disabled radio, and either would then be posted to `/runs/preflight` and `/runs`.
 */
export function reconcileInitial(
  state: FormState,
  projects: components['schemas']['ProjectRead'][],
  harnesses: HarnessOut[],
  catalog: TemplateCatalog,
): FormState {
  const repositories = repositoriesFor(projects, state.projectId);
  const repository = repositoryById(repositories, state.repositoryId);
  const harnessEnabled = harnesses.some(
    (candidate) => candidate.name === state.harness && candidate.enabled,
  );
  return {
    ...state,
    repositoryId: repository ? state.repositoryId : '',
    // the brief's own rule: "a disabled harness is not selectable"
    harness: harnessEnabled && usesHarness(state.template, catalog) ? state.harness : '',
    // "base branch (default: repository default branch)" — seeded when the link named a
    // Repository but no branch, so a real prefill link opens a startable form
    baseBranch: state.baseBranch || repository?.default_branch || '',
  };
}
