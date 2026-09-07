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

/** Switching template keeps every field but the inputs the new template does not have. */
export function withTemplate(state: FormState, template: TemplateName): FormState {
  const fields = TEMPLATE_INPUT_FIELDS[template];
  const inputs: Record<string, string> = {};
  for (const field of fields) inputs[field.key] = state.inputs[field.key] ?? '';
  return { ...state, template, inputs };
}

export function withInput(state: FormState, key: string, value: string): FormState {
  return { ...state, inputs: { ...state.inputs, [key]: value } };
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

/** The test-id suffix for one check line: lower-kebab, so `"origin reachable"` becomes
 * `origin-reachable` and the id stays a single CSS-safe token. */
export function checkSlug(check: string): string {
  return check.trim().toLowerCase().replace(/\s+/g, '-');
}

/** `{name} · enabled | disabled: {failing_check or "no readiness run"} · last readiness
 * {time or —} · re-run readiness` — the brief's own line, verbatim. */
export function harnessLine(harness: HarnessOut): string {
  const status = harness.enabled
    ? 'enabled'
    : `disabled: ${harness.failing_check ?? 'no readiness run'}`;
  const readiness = harness.last_readiness_at ? readinessTime(harness.last_readiness_at) : '—';
  return `${harness.name} · ${status} · last readiness ${readiness} · re-run readiness`;
}

function readinessTime(iso: string): string {
  return iso.slice(0, 19).replace('T', ' ');
}
