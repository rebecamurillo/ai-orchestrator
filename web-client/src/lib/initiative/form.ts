/**
 * Pure state for the New Initiative form (S7): no DOM, no fetch, so it unit-tests without
 * rendering (`web-client/AGENTS.md`) — the same split `src/lib/newwf/state.ts` documents for
 * the New Workflow form this one mirrors.
 *
 * There is no per-template catalog here (`newwf/catalog.ts`'s own reason to exist): the
 * initiative form's fields are fixed by `InitiativeIn` itself, never derived from a
 * Template's declared `inputs`.
 */
import type { components } from '../../api/schema';

type InitiativeIn = components['schemas']['InitiativeIn'];
type ProjectRead = components['schemas']['ProjectRead'];
type RepositoryOut = components['schemas']['RepositoryOut'];

/** `InitiativeIn`'s own defaults for the three Template fields the form exposes no control
 * for (S7's scope list names five fields — project, hub repository, folder, base branch,
 * harness, model, budget — none of the three) — the same literals the generated schema's
 * `@default` carries. */
export const DEFAULT_EPIC_TEMPLATE = 'epic';
export const DEFAULT_MERGE_TEMPLATE = 'merge';
export const DEFAULT_GOLIVE_TEMPLATE = 'golive';

export interface FormState {
  projectId: string;
  /** The **hub** repository: where `{initiativeFolder}/epics.yaml` lives. */
  repositoryId: string;
  initiativeFolder: string;
  baseBranch: string;
  harness: string;
  model: string;
  budgetUsdPerEpic: string;
}

export function defaultFormState(): FormState {
  return {
    projectId: '',
    repositoryId: '',
    initiativeFolder: '',
    baseBranch: '',
    harness: '',
    model: '',
    budgetUsdPerEpic: '',
  };
}

/** The Repositories of the selected Project, or none while nothing is selected —
 * `newwf/state.ts::repositoriesFor`'s own reading, duplicated rather than imported: it is a
 * two-line derivation over `ProjectRead[]`, and importing across a feature boundary for that
 * would couple two forms that otherwise share nothing (`board/format.ts::tokenSignal`'s own
 * documented convention for a small duplication like this one). */
export function repositoriesFor(projects: ProjectRead[], projectId: string): RepositoryOut[] {
  return projects.find((project) => project.id === projectId)?.repositories ?? [];
}

export function repositoryById(
  repositories: RepositoryOut[],
  repositoryId: string,
): RepositoryOut | undefined {
  return repositories.find((repository) => repository.id === repositoryId);
}

/** Whether every field `InitiativeIn` requires is filled. `project_id`/`repository_id` are
 * `format: uuid` and not nullable on the wire — unlike `newwf/state.ts::preflightBody`,
 * whose `PreflightIn` accepts `null` for the equivalent fields, there is no partial shape
 * either endpoint here can be asked to answer, so an incomplete form must never reach either
 * one at all. */
export function isComplete(state: FormState): boolean {
  return (
    state.projectId !== '' &&
    state.repositoryId !== '' &&
    state.baseBranch.trim() !== '' &&
    state.initiativeFolder.trim() !== ''
  );
}

/** The one body both `POST /initiatives/preflight` and `POST /initiatives` take (the
 * endpoint contract's own "share one body") — `null` while `isComplete` is false, so the
 * island never calls either endpoint with a shape it would refuse outright. */
export function buildBody(state: FormState): InitiativeIn | null {
  if (!isComplete(state)) return null;
  return {
    project_id: state.projectId,
    repository_id: state.repositoryId,
    base_branch: state.baseBranch,
    initiative_folder: state.initiativeFolder,
    epic_template: DEFAULT_EPIC_TEMPLATE,
    merge_template: DEFAULT_MERGE_TEMPLATE,
    golive_template: DEFAULT_GOLIVE_TEMPLATE,
    harness: state.harness || null,
    model: state.model || null,
    budget_usd_per_epic: state.budgetUsdPerEpic || null,
  };
}
