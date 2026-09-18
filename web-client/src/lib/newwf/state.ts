/**
 * Pure state for the New Workflow form (4.13, UX-DR8) — no DOM, no fetch, so it unit-tests
 * without rendering (`web-client/AGENTS.md`).
 *
 * `TEMPLATE_ORDER` and `TEMPLATE_INPUT_FIELDS` are the brief's own fixed enumeration, not
 * derived from `GET /templates`: this epic ships exactly three root Templates
 * (`templates/initiative.yaml`, `templates/epic.yaml`, `templates/repo-init.yaml`), `story`
 * is never started directly, and the list the Operator switches between never depends on
 * what the list endpoint happens to answer. The `templates` prop is read only to look up
 * `latest_version` for whichever name is selected.
 */
import type { components } from '../../api/schema';

type LineOut = components['schemas']['LineOut'];
type PreflightIn = components['schemas']['PreflightIn'];
type RunIn = components['schemas']['RunIn'];
type TemplateSummary = components['schemas']['TemplateSummaryOut'];
type RepositoryOut = components['schemas']['RepositoryOut'];
type HarnessOut = components['schemas']['HarnessOut'];
export type ProbeResultOut = components['schemas']['ProbeResultOut'];

export const TEMPLATE_ORDER = ['initiative', 'epic', 'repo-init'] as const;
export type TemplateName = (typeof TEMPLATE_ORDER)[number];

export const DEFAULT_TEMPLATE: TemplateName = 'initiative';

export interface TemplateInputField {
  key: string;
  label: string;
}

/** Template-dependent inputs, in the brief's own words and order. */
export const TEMPLATE_INPUT_FIELDS: Record<TemplateName, TemplateInputField[]> = {
  initiative: [{ key: 'initiative_folder', label: 'INITIATIVE FOLDER' }],
  epic: [
    { key: 'branch', label: 'WORKING BRANCH' },
    { key: 'spec_folder', label: 'SPEC FOLDER' },
  ],
  'repo-init': [],
};

export function isTemplateName(value: string): value is TemplateName {
  return (TEMPLATE_ORDER as readonly string[]).includes(value);
}

export interface FormState {
  template: TemplateName;
  projectId: string;
  repositoryId: string;
  baseBranch: string;
  /** Keyed by `TEMPLATE_INPUT_FIELDS[template]`'s own `key`s; a field the current template
   * does not declare is dropped rather than carried across a template change. */
  inputs: Record<string, string>;
  harness: string;
  model: string;
  budgetUsd: string;
  reReviewDone: boolean;
  manualEstimateH: string;
}

export function defaultFormState(): FormState {
  const inputs: Record<string, string> = {};
  for (const field of TEMPLATE_INPUT_FIELDS[DEFAULT_TEMPLATE]) inputs[field.key] = '';
  return {
    template: DEFAULT_TEMPLATE,
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

/** Whether this Template dispatches to a harness at all — `repo-init` runs no agent step,
 * so the brief hides its harness list entirely. */
export function usesHarness(template: TemplateName): boolean {
  return template !== 'repo-init';
}

/**
 * Switching template keeps every field but the inputs the new template does not have, and
 * clears `harness` for a template whose form has no harness list: hiding the control while
 * still submitting its value would post a harness the Operator can no longer see or change.
 */
export function withTemplate(state: FormState, template: TemplateName): FormState {
  const fields = TEMPLATE_INPUT_FIELDS[template];
  const inputs: Record<string, string> = {};
  for (const field of fields) inputs[field.key] = state.inputs[field.key] ?? '';
  return { ...state, template, inputs, harness: usesHarness(template) ? state.harness : '' };
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
 * calling it before `start_allowed` could ever be true. */
export function runBody(state: FormState, templates: TemplateSummary[]): RunIn | null {
  const version = latestVersion(templates, state.template);
  if (!state.projectId || !state.repositoryId || !state.baseBranch || !state.budgetUsd) {
    return null;
  }
  if (version === undefined) return null;
  return {
    template_name: state.template,
    template_version: version,
    project_id: state.projectId,
    repository_id: state.repositoryId,
    base_branch: state.baseBranch,
    budget_usd: state.budgetUsd,
    inputs: state.inputs,
    harness: state.harness || null,
    model: state.model || null,
    manual_estimate_h: state.manualEstimateH || null,
    re_review_done: state.reReviewDone,
  };
}

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
    harness: harnessEnabled && usesHarness(state.template) ? state.harness : '',
    // "base branch (default: repository default branch)" — seeded when the link named a
    // Repository but no branch, so a real prefill link opens a startable form
    baseBranch: state.baseBranch || repository?.default_branch || '',
  };
}
