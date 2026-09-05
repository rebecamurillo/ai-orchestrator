/**
 * The pure functions behind `ProjectForm.tsx` (2.5) — row add, mask/replace toggle,
 * hidden-input name generation, error lookup by path, and the `initial`-prop builders —
 * exercised directly with no DOM, per `vitest.config.ts`'s `environment: 'node'`.
 */
import { describe, expect, it } from 'vitest';

import {
  DEFAULT_PACKAGE_MANAGER,
  DEFAULT_TEST_GLOBS,
  addRow,
  emptyEnvVarRow,
  emptyRepositoryRow,
  envVarFieldName,
  findError,
  initialEnvVarRows,
  initialRepositoryRows,
  repositoryFieldName,
  startReplacingEnvVar,
  type EnvVarRowState,
  type ProjectFormInitial,
} from '../../src/islands/project-form-logic';

describe('addRow', () => {
  it('appends, never inserts or removes (add-only)', () => {
    const rows = [1, 2];

    expect(addRow(rows, 3)).toEqual([1, 2, 3]);
    expect(rows).toEqual([1, 2]);
  });
});

describe('emptyEnvVarRow', () => {
  it('starts revealed: a new row has nothing stored to keep', () => {
    expect(emptyEnvVarRow()).toEqual({ name: '', value: '', replacing: true });
  });
});

describe('emptyRepositoryRow', () => {
  it('pre-fills the three protected globs and the default package manager', () => {
    const row = emptyRepositoryRow();

    expect(row.testGlobs).toBe(DEFAULT_TEST_GLOBS);
    expect(row.packageManager).toBe(DEFAULT_PACKAGE_MANAGER);
    expect(row.url).toBe('');
    expect(row.defaultBranch).toBe('');
    expect(row.id).toBeUndefined();
  });
});

describe('startReplacingEnvVar', () => {
  const stored: EnvVarRowState[] = [
    { name: 'A', value: '', masked: '****1234', replacing: false },
    { name: 'B', value: '', masked: '****5678', replacing: false },
  ];

  it('reveals an empty value input for the targeted row only', () => {
    const next = startReplacingEnvVar(stored, 1);

    expect(next[0]).toEqual(stored[0]);
    expect(next[1]).toEqual({ name: 'B', value: '', masked: '****5678', replacing: true });
  });

  it('does not mutate the row array it was given', () => {
    startReplacingEnvVar(stored, 0);

    expect(stored[0]!.replacing).toBe(false);
  });
});

describe('envVarFieldName', () => {
  it('names the row by index and field', () => {
    expect(envVarFieldName(0, 'name')).toBe('env_vars[0].name');
    expect(envVarFieldName(2, 'value')).toBe('env_vars[2].value');
    expect(envVarFieldName(1, 'masked')).toBe('env_vars[1].masked');
  });
});

describe('repositoryFieldName', () => {
  it('names the row by index and field, matching what the Action remaps a path onto', () => {
    expect(repositoryFieldName(1, 'default_branch')).toBe('repositories[1].default_branch');
    expect(repositoryFieldName(0, 'url')).toBe('repositories[0].url');
  });
});

describe('findError', () => {
  const errors = [
    { path: 'repositories[1].default_branch', reason: 'required' },
    { path: 'env_vars[0].name', reason: 'instance setting, not a project variable' },
    { path: null, reason: 'whole-body reason' },
  ];

  it('finds the one error whose path matches the field name', () => {
    expect(findError(errors, 'repositories[1].default_branch')).toEqual(errors[0]);
    expect(findError(errors, 'env_vars[0].name')).toEqual(errors[1]);
  });

  it('finds nothing for a field with no error', () => {
    expect(findError(errors, 'repositories[0].url')).toBeUndefined();
  });

  it('finds nothing when there is no errors array at all', () => {
    expect(findError(undefined, 'name')).toBeUndefined();
  });
});

describe('initialEnvVarRows', () => {
  it('starts a stored, masked row unrevealed', () => {
    const initial: ProjectFormInitial = {
      name: '',
      contextText: '',
      contextPaths: '',
      logPromptContent: false,
      envVars: [{ name: 'NODE_ENV', masked: '****ion' }],
      repositories: [],
    };

    expect(initialEnvVarRows(initial)).toEqual([
      { name: 'NODE_ENV', masked: '****ion', value: '', replacing: false },
    ]);
  });

  it('starts a kept draft row with no mask revealed, carrying its typed value forward', () => {
    const initial: ProjectFormInitial = {
      name: '',
      contextText: '',
      contextPaths: '',
      logPromptContent: false,
      envVars: [{ name: 'NEW_VAR', value: 'typed-value' }],
      repositories: [],
    };

    expect(initialEnvVarRows(initial)).toEqual([
      { name: 'NEW_VAR', masked: undefined, value: 'typed-value', replacing: true },
    ]);
  });
});

describe('initialRepositoryRows', () => {
  it('carries every field of a stored repository row through unchanged', () => {
    const initial: ProjectFormInitial = {
      name: '',
      contextText: '',
      contextPaths: '',
      logPromptContent: false,
      envVars: [],
      repositories: [
        {
          id: 'repo-1',
          url: 'https://github.com/example/repo.git',
          defaultBranch: 'main',
          packageManager: 'pnpm',
          testGlobs: DEFAULT_TEST_GLOBS,
          installCommand: 'pnpm install',
          qualityGateCommand: 'pnpm lint',
          unitTestCommand: 'pnpm test',
        },
      ],
    };

    const rows = initialRepositoryRows(initial);

    expect(rows).toEqual(initial.repositories);
    expect(rows).not.toBe(initial.repositories);
  });
});
