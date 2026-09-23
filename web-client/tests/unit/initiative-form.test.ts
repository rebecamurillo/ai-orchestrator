/**
 * `src/lib/initiative/form.ts` (S7): the New Initiative form's pure state and the one body
 * both `POST /initiatives/preflight` and `POST /initiatives` share.
 */
import { describe, expect, it } from 'vitest';

import {
  DEFAULT_EPIC_TEMPLATE,
  DEFAULT_GOLIVE_TEMPLATE,
  DEFAULT_MERGE_TEMPLATE,
  buildBody,
  defaultFormState,
  isComplete,
  repositoriesFor,
  repositoryById,
  type FormState,
} from '../../src/lib/initiative/form';
import type { components } from '../../src/api/schema';

type ProjectRead = components['schemas']['ProjectRead'];
type RepositoryOut = components['schemas']['RepositoryOut'];

function repository(overrides: Partial<RepositoryOut> = {}): RepositoryOut {
  return {
    id: 'repo-1',
    project_id: 'project-1',
    slug: 'repo',
    url: 'https://github.com/example/repo.git',
    default_branch: 'main',
    install_command: '',
    quality_gate_command: '',
    unit_test_command: '',
    test_globs: [],
    package_manager: 'other',
    clone_check: { status: 'ok', at: null, output: '', bmad_version: null },
    clone_check_lines: [],
    clone_check_hint: '',
    verify_skipped: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function project(overrides: Partial<ProjectRead> = {}): ProjectRead {
  return {
    id: 'project-1',
    slug: 'project',
    name: 'Demo',
    context_text: '',
    context_paths: [],
    env_vars: [],
    log_prompt_content: false,
    repositories: [repository()],
    runs: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function complete(overrides: Partial<FormState> = {}): FormState {
  return {
    projectId: 'project-1',
    repositoryId: 'repo-1',
    initiativeFolder: 'docs/initiative',
    baseBranch: 'main',
    harness: '',
    model: '',
    budgetUsdPerEpic: '',
    ...overrides,
  };
}

describe('defaultFormState', () => {
  it('opens every field blank', () => {
    expect(defaultFormState()).toEqual({
      projectId: '',
      repositoryId: '',
      initiativeFolder: '',
      baseBranch: '',
      harness: '',
      model: '',
      budgetUsdPerEpic: '',
    });
  });
});

describe('repositoriesFor / repositoryById', () => {
  it('finds the selected project’s repositories, and none while nothing is selected', () => {
    const projects = [project()];

    expect(repositoriesFor(projects, 'project-1')).toEqual([repository()]);
    expect(repositoriesFor(projects, '')).toEqual([]);
    expect(repositoriesFor(projects, 'missing')).toEqual([]);
  });

  it('finds one repository by id, or answers undefined', () => {
    const repositories = [repository()];

    expect(repositoryById(repositories, 'repo-1')).toEqual(repository());
    expect(repositoryById(repositories, 'missing')).toBeUndefined();
  });
});

describe('isComplete', () => {
  it('is true once every required field is filled', () => {
    expect(isComplete(complete())).toBe(true);
  });

  it('is false with no project selected', () => {
    expect(isComplete(complete({ projectId: '' }))).toBe(false);
  });

  it('is false with no hub repository selected', () => {
    expect(isComplete(complete({ repositoryId: '' }))).toBe(false);
  });

  it('is false with a blank (or whitespace-only) base branch', () => {
    expect(isComplete(complete({ baseBranch: '' }))).toBe(false);
    expect(isComplete(complete({ baseBranch: '   ' }))).toBe(false);
  });

  it('is false with a blank (or whitespace-only) initiative folder', () => {
    expect(isComplete(complete({ initiativeFolder: '' }))).toBe(false);
    expect(isComplete(complete({ initiativeFolder: '   ' }))).toBe(false);
  });
});

describe('buildBody', () => {
  it('is null while the form is incomplete — neither endpoint is ever called with it', () => {
    expect(buildBody(complete({ projectId: '' }))).toBeNull();
  });

  it('fills the three Template fields with their own generated defaults', () => {
    const body = buildBody(complete());

    expect(body?.epic_template).toBe(DEFAULT_EPIC_TEMPLATE);
    expect(body?.merge_template).toBe(DEFAULT_MERGE_TEMPLATE);
    expect(body?.golive_template).toBe(DEFAULT_GOLIVE_TEMPLATE);
  });

  it('nulls harness, model and budget when the Operator left them blank', () => {
    const body = buildBody(complete());

    expect(body).toMatchObject({
      project_id: 'project-1',
      repository_id: 'repo-1',
      base_branch: 'main',
      initiative_folder: 'docs/initiative',
      harness: null,
      model: null,
      budget_usd_per_epic: null,
    });
  });

  it('carries harness, model and budget through when the Operator set them', () => {
    const body = buildBody(
      complete({ harness: 'claude', model: 'opus', budgetUsdPerEpic: '25.00' }),
    );

    expect(body).toMatchObject({ harness: 'claude', model: 'opus', budget_usd_per_epic: '25.00' });
  });
});
