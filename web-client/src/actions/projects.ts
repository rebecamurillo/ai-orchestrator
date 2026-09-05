/**
 * The `save` Action behind `ProjectForm.tsx` (2.5): one native form post, orchestrating
 * every per-resource API call a create or an update needs, then handing the page back
 * either a redirect target or everything the form needs to re-render with nothing lost.
 *
 * Manual `FormData` parsing, no `zod` — the pattern `src/actions/login.ts` and
 * `src/actions/repositories.ts` already use, and the boundary this story's brief settles
 * explicitly (no new dependency).
 *
 * **Why the required-field checks below run before any backend call.** `url` and
 * `default_branch` are the two Repository fields the backend itself refuses empty
 * (`RepositoryWrite.default_branch: Field(min_length=1)`), and a submission's two rows
 * sharing a `url` is refused by the backend too, once both are stored — but "create then
 * check" would mean the *first* repository in a bad submission is already written by the
 * time the *second* one is refused, breaking the matrix's "nothing is created". Checking
 * these three things against the submission itself, before the first `fetch`, is what
 * makes that claim true regardless of row order.
 *
 * **Why a glob or a reserved env-var name is not checked here too.** Both are real backend
 * rules (`domain/rules/globs.py`, `domain/entities/project.py`) this Action does not
 * restate; it calls the backend and relays whatever `errors[]` comes back, remapped onto
 * the row that sent it. A partial write ahead of that refusal is accepted, exactly as the
 * story's I/O matrix states it (only the required-field and duplicate-url cases claim
 * atomicity).
 *
 * **Why every write is followed by its own `clone-check`.** `run_clone_checks_for_project`
 * (2.3) only fires from `POST`/`PUT /api/v1/projects/{id}`, which commits before any
 * Repository exists on a create — so without this Action's own explicit
 * `POST /repositories/{id}/clone-check` after each write, every new Repository would read
 * `pending` and the readout would never show a fresh line (Design Notes).
 */
import { ActionError, defineAction } from 'astro:actions';

import type { components } from '../api/schema';
import { backend } from '../api/server';
import type { ProjectFormInitial } from '../islands/project-form-logic';

type ProblemDetail = components['schemas']['ProblemDetail'];
type RepositoryWriteBody = components['schemas']['RepositoryCreate'];
type PackageManager = RepositoryWriteBody['package_manager'];

export interface EnvVarDraft {
  name: string;
  /** Absent means "kept" on an update; always present on a create's revealed rows. */
  value?: string;
  /** The stored mask, carried forward only so a kept row can be redisplayed unrevealed. */
  masked?: string;
}

export interface RepositoryDraft {
  /** Present for an existing, stored Repository; absent for a row added this session. */
  id?: string;
  url: string;
  defaultBranch: string;
  packageManager: string;
  testGlobs: string;
  installCommand: string;
  qualityGateCommand: string;
  unitTestCommand: string;
}

export interface ProjectDraft {
  mode: 'create' | 'edit';
  projectId?: string;
  name: string;
  contextText: string;
  contextPaths: string;
  logPromptContent: boolean;
  envVars: EnvVarDraft[];
  repositories: RepositoryDraft[];
}

export interface SaveFieldError {
  path?: string | null;
  reason: string;
}

/** Everything `ActionError.message` JSON-encodes on failure (Design Notes). */
export interface SaveFailure {
  draft: ProjectDraft;
  detail?: string;
  errors?: SaveFieldError[];
}

export interface SaveResult {
  id: string;
  slug: string;
}

/** `draft` reconstructed as `ProjectForm`'s `initial` prop, so a failed round trip keeps
 * every value the Operator typed — the only source of that prop after an error. */
export function draftToInitial(draft: ProjectDraft): ProjectFormInitial {
  return {
    projectId: draft.projectId,
    name: draft.name,
    contextText: draft.contextText,
    contextPaths: draft.contextPaths,
    logPromptContent: draft.logPromptContent,
    envVars: draft.envVars.map((row) => ({
      name: row.name,
      masked: row.masked,
      value: row.value,
    })),
    repositories: draft.repositories.map((row) => ({ ...row })),
  };
}

const REQUIRED_REASON = 'required';
const DUPLICATE_URL_DETAIL = 'two repositories in this submission share the same url';

function formString(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === 'string' ? value : '';
}

function formStringOrUndefined(form: FormData, name: string): string | undefined {
  const value = form.get(name);
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

/** Non-empty, newline-separated lines, trimmed — used for `context_paths` and `test_globs`. */
function nonEmptyLines(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

const ENV_VAR_KEY = /^env_vars\[(\d+)\]\.(name|value|masked)$/;
const REPOSITORY_KEY = /^repositories\[(\d+)\]\.(.+)$/;

function collectEnvVars(form: FormData): EnvVarDraft[] {
  const byIndex = new Map<number, EnvVarDraft>();
  for (const key of form.keys()) {
    const match = ENV_VAR_KEY.exec(key);
    if (!match) continue;
    const index = Number(match[1]);
    const field = match[2] as 'name' | 'value' | 'masked';
    const row = byIndex.get(index) ?? { name: '' };
    if (field === 'name') row.name = formString(form, key);
    else if (field === 'value') row.value = formString(form, key);
    else row.masked = formString(form, key);
    byIndex.set(index, row);
  }
  return [...byIndex.entries()].sort(([a], [b]) => a - b).map(([, row]) => row);
}

interface RepositoryDraftBuilder extends Partial<RepositoryDraft> {
  index: number;
}

function collectRepositories(form: FormData): RepositoryDraft[] {
  const byIndex = new Map<number, RepositoryDraftBuilder>();
  for (const key of form.keys()) {
    const match = REPOSITORY_KEY.exec(key);
    if (!match) continue;
    const index = Number(match[1]);
    const field = match[2];
    const row = byIndex.get(index) ?? { index };
    const value = formString(form, key);
    switch (field) {
      case 'id':
        row.id = value || undefined;
        break;
      case 'url':
        row.url = value;
        break;
      case 'default_branch':
        row.defaultBranch = value;
        break;
      case 'package_manager':
        row.packageManager = value;
        break;
      case 'test_globs':
        row.testGlobs = value;
        break;
      case 'install_command':
        row.installCommand = value;
        break;
      case 'quality_gate_command':
        row.qualityGateCommand = value;
        break;
      case 'unit_test_command':
        row.unitTestCommand = value;
        break;
      default:
        break;
    }
    byIndex.set(index, row);
  }
  return [...byIndex.entries()]
    .sort(([a], [b]) => a - b)
    .map(([, row]) => ({
      id: row.id,
      url: row.url ?? '',
      defaultBranch: row.defaultBranch ?? '',
      packageManager: row.packageManager ?? 'other',
      testGlobs: row.testGlobs ?? '',
      installCommand: row.installCommand ?? '',
      qualityGateCommand: row.qualityGateCommand ?? '',
      unitTestCommand: row.unitTestCommand ?? '',
    }));
}

function parseDraft(form: FormData): ProjectDraft {
  return {
    mode: formString(form, 'mode') === 'edit' ? 'edit' : 'create',
    projectId: formStringOrUndefined(form, 'project_id'),
    name: formString(form, 'name'),
    contextText: formString(form, 'context_text'),
    contextPaths: formString(form, 'context_paths'),
    logPromptContent: formString(form, 'log_prompt_content') === 'on',
    envVars: collectEnvVars(form),
    repositories: collectRepositories(form),
  };
}

/** The two required-field rules the backend also enforces (`Field(min_length=1)`), checked
 * against the whole submission before any call is made — see the module docstring. */
function requiredFieldErrors(draft: ProjectDraft): SaveFieldError[] {
  const errors: SaveFieldError[] = [];
  if (draft.name.trim().length === 0) errors.push({ path: 'name', reason: REQUIRED_REASON });

  draft.repositories.forEach((repository, index) => {
    if (repository.url.trim().length === 0) {
      errors.push({ path: `repositories[${index}].url`, reason: REQUIRED_REASON });
    }
    if (repository.defaultBranch.trim().length === 0) {
      errors.push({ path: `repositories[${index}].default_branch`, reason: REQUIRED_REASON });
    }
  });
  return errors;
}

/** Two rows of the same submission naming the same URL, before anything is created. */
function duplicateUrlDetail(draft: ProjectDraft): string | undefined {
  const seen = new Set<string>();
  for (const repository of draft.repositories) {
    const url = repository.url.trim();
    if (url.length === 0) continue;
    if (seen.has(url)) return DUPLICATE_URL_DETAIL;
    seen.add(url);
  }
  return undefined;
}

function fail(draft: ProjectDraft, failure: Omit<SaveFailure, 'draft'>): never {
  const hasFieldErrors = Boolean(failure.errors && failure.errors.length > 0);
  throw new ActionError({
    code: hasFieldErrors ? 'BAD_REQUEST' : 'CONFLICT',
    message: JSON.stringify({ draft, ...failure } satisfies SaveFailure),
  });
}

/** `body.env_vars.0.name` -> `env_vars[0].name`; `default_branch` -> `repositories[1].default_branch`
 * when called for the row at that index. This is the one remap every backend `path` goes
 * through, so `findError` needs no per-field special-casing on the page (Design Notes). */
function normalizePath(rawPath: string, repositoryIndex?: number): string {
  const withoutBody = rawPath.startsWith('body.') ? rawPath.slice('body.'.length) : rawPath;
  const bracketed = withoutBody.replace(/\.(\d+)(?=\.|$)/g, '[$1]');
  return repositoryIndex === undefined
    ? bracketed
    : `repositories[${repositoryIndex}].${bracketed}`;
}

function toFailure(problem: ProblemDetail, repositoryIndex?: number): Omit<SaveFailure, 'draft'> {
  if (!problem.errors || problem.errors.length === 0) {
    return { detail: problem.detail ?? problem.title };
  }
  return {
    detail: problem.detail ?? undefined,
    errors: problem.errors.map((entry) => ({
      reason: entry.reason,
      path: entry.path ? normalizePath(entry.path, repositoryIndex) : undefined,
    })),
  };
}

function repositoryBody(repository: RepositoryDraft): RepositoryWriteBody {
  return {
    url: repository.url,
    default_branch: repository.defaultBranch,
    package_manager: repository.packageManager as PackageManager,
    test_globs: nonEmptyLines(repository.testGlobs),
    install_command: repository.installCommand,
    quality_gate_command: repository.qualityGateCommand,
    unit_test_command: repository.unitTestCommand,
  };
}

type Backend = ReturnType<typeof backend>;

/** Fire-and-forget by design: 2.3's own rule is "a failing check never fails the save", so
 * this Action never inspects the result — the readout is what shows a failed line. A
 * `{error}` response already falls out of that (nothing here reads `error`); a *thrown*
 * exception (a network failure, say) is caught too, for the same reason — the Project and
 * its Repositories are already stored by the time this runs, and a check that could not
 * even be attempted is no more a reason to fail the save than one that came back failed. */
async function triggerCloneChecks(client: Backend, repositoryIds: string[]): Promise<void> {
  for (const repositoryId of repositoryIds) {
    try {
      await client.POST('/api/v1/repositories/{repository_id}/clone-check', {
        params: { path: { repository_id: repositoryId } },
      });
    } catch {
      // swallowed on purpose — see the function docstring
    }
  }
}

/** The final read the save flow ends on. A thrown exception here falls back to the id and
 * slug already known from the write that just succeeded, exactly as a missing `data` does —
 * the read is a courtesy for a fresher body, never a condition of the save itself. */
async function readProject(
  client: Backend,
  projectId: string,
  fallbackSlug: string,
): Promise<SaveResult> {
  try {
    const { data } = await client.GET('/api/v1/projects/{project_id}', {
      params: { path: { project_id: projectId } },
    });
    return { id: data?.id ?? projectId, slug: data?.slug ?? fallbackSlug };
  } catch {
    return { id: projectId, slug: fallbackSlug };
  }
}

async function createFlow(client: Backend, draft: ProjectDraft): Promise<SaveResult> {
  const { data: project, error } = await client.POST('/api/v1/projects', {
    body: {
      name: draft.name,
      context_text: draft.contextText,
      context_paths: nonEmptyLines(draft.contextPaths),
      log_prompt_content: draft.logPromptContent,
      env_vars: draft.envVars.map((row) => ({ name: row.name, value: row.value ?? '' })),
    },
  });
  if (error || !project) fail(draft, toFailure(error!));

  const createdRepositoryIds: string[] = [];
  for (const [index, repository] of draft.repositories.entries()) {
    const { data: created, error: repositoryError } = await client.POST(
      '/api/v1/projects/{project_id}/repositories',
      { params: { path: { project_id: project.id } }, body: repositoryBody(repository) },
    );
    if (repositoryError || !created) fail(draft, toFailure(repositoryError!, index));
    createdRepositoryIds.push(created.id);
  }

  await triggerCloneChecks(client, createdRepositoryIds);
  return readProject(client, project.id, project.slug);
}

async function updateFlow(client: Backend, draft: ProjectDraft): Promise<SaveResult> {
  const projectId = draft.projectId!;
  const { data: project, error } = await client.PUT('/api/v1/projects/{project_id}', {
    params: { path: { project_id: projectId } },
    body: {
      name: draft.name,
      context_text: draft.contextText,
      context_paths: nonEmptyLines(draft.contextPaths),
      log_prompt_content: draft.logPromptContent,
      env_vars: draft.envVars.map((row) => ({ name: row.name, value: row.value })),
    },
  });
  if (error || !project) fail(draft, toFailure(error!));

  const touchedRepositoryIds: string[] = [];
  for (const [index, repository] of draft.repositories.entries()) {
    if (repository.id) {
      const { data: updated, error: repositoryError } = await client.PUT(
        '/api/v1/repositories/{repository_id}',
        { params: { path: { repository_id: repository.id } }, body: repositoryBody(repository) },
      );
      if (repositoryError || !updated) fail(draft, toFailure(repositoryError!, index));
      touchedRepositoryIds.push(updated.id);
    } else {
      const { data: created, error: repositoryError } = await client.POST(
        '/api/v1/projects/{project_id}/repositories',
        { params: { path: { project_id: projectId } }, body: repositoryBody(repository) },
      );
      if (repositoryError || !created) fail(draft, toFailure(repositoryError!, index));
      touchedRepositoryIds.push(created.id);
    }
  }

  await triggerCloneChecks(client, touchedRepositoryIds);
  return readProject(client, projectId, project.slug);
}

export const save = defineAction({
  accept: 'form',
  handler: async (form: FormData): Promise<SaveResult> => {
    const draft = parseDraft(form);

    const fieldErrors = requiredFieldErrors(draft);
    if (fieldErrors.length > 0) fail(draft, { errors: fieldErrors });

    const duplicate = duplicateUrlDetail(draft);
    if (duplicate) fail(draft, { detail: duplicate });

    const client = backend();
    return draft.mode === 'create' ? createFlow(client, draft) : updateFlow(client, draft);
  },
});
