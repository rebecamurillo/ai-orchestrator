/**
 * Pure functions behind `ProjectForm.tsx`, in a sibling module for one reason:
 * `vitest.config.ts` runs with `test.environment: 'node'` and no DOM-mounting library, so
 * the island's row-management, mask/replace toggle, hidden-input naming, and error-path
 * lookup are exported here as plain functions and unit-tested directly, never mounted
 * (story 2.5).
 *
 * Nothing here imports React, `astro:actions`, or `../api/server` — this module has to stay
 * importable from both the browser island and the server-side Action without pulling either
 * side's dependencies into the other.
 */

/** One `errors[]` entry, as `ProblemError` and the Action's own synthesized errors share. */
export interface FieldError {
  path?: string | null;
  reason: string;
}

/** `errors.find(e => e.path === fieldName)` — the one lookup every field error uses. */
export function findError(errors: FieldError[] | undefined, path: string): FieldError | undefined {
  return errors?.find((error) => error.path === path);
}

/** The three globs `test_globs` starts with (the backend merges these in regardless). */
export const DEFAULT_TEST_GLOBS = 'tests/**\n**/*.test.*\n**/*.spec.*';

export const DEFAULT_PACKAGE_MANAGER = 'other';

/** One env-var row's UI state: a stored, masked row until `replacing` reveals a value input. */
export interface EnvVarRowState {
  name: string;
  value: string;
  /** Set only for a row that started out stored; absent for a brand-new row. */
  masked?: string;
  /** True for a new row, or a stored row whose *replace* affordance was used. */
  replacing: boolean;
}

/** One repository row's UI state. Every field is a plain form value; nothing is derived. */
export interface RepositoryRowState {
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

/** A freshly added env-var row: no stored value to keep, so it starts revealed. */
export function emptyEnvVarRow(): EnvVarRowState {
  return { name: '', value: '', replacing: true };
}

/** A freshly added repository row, pre-filled with the three protected globs. */
export function emptyRepositoryRow(): RepositoryRowState {
  return {
    url: '',
    defaultBranch: '',
    packageManager: DEFAULT_PACKAGE_MANAGER,
    testGlobs: DEFAULT_TEST_GLOBS,
    installCommand: '',
    qualityGateCommand: '',
    unitTestCommand: '',
  };
}

/** Add-only: every row-add in this product appends, never inserts or removes. */
export function addRow<T>(rows: T[], row: T): T[] {
  return [...rows, row];
}

/** The *replace* affordance: reveals an empty value input for one stored, masked row. */
export function startReplacingEnvVar(rows: EnvVarRowState[], index: number): EnvVarRowState[] {
  return rows.map((row, i) => (i === index ? { ...row, replacing: true, value: '' } : row));
}

/** `env_vars[n].name` / `env_vars[n].value` / `env_vars[n].masked` (kept-value redisplay only). */
export function envVarFieldName(index: number, field: 'name' | 'value' | 'masked'): string {
  return `env_vars[${index}].${field}`;
}

export type RepositoryField =
  | 'id'
  | 'url'
  | 'default_branch'
  | 'package_manager'
  | 'test_globs'
  | 'install_command'
  | 'quality_gate_command'
  | 'unit_test_command';

/** `repositories[n].<field>` — the exact name the Action remaps a backend `path` onto. */
export function repositoryFieldName(index: number, field: RepositoryField): string {
  return `repositories[${index}].${field}`;
}

// ── initial props, from either a stored Project or a kept draft ──────────────────────────

export interface ProjectFormEnvVarInitial {
  name: string;
  /** A stored variable's mask (`••••1234`); absent for a new or already-replaced row. */
  masked?: string;
  value?: string;
}

export interface ProjectFormRepositoryInitial {
  id?: string;
  url: string;
  defaultBranch: string;
  packageManager: string;
  testGlobs: string;
  installCommand: string;
  qualityGateCommand: string;
  unitTestCommand: string;
}

/** `ProjectForm`'s `initial` prop — built from `ProjectRead` on a fresh load, or from a
 * kept draft after a failed save (`src/actions/projects.ts`'s `draftToInitial`). */
export interface ProjectFormInitial {
  projectId?: string;
  name: string;
  contextText: string;
  contextPaths: string;
  logPromptContent: boolean;
  envVars: ProjectFormEnvVarInitial[];
  repositories: ProjectFormRepositoryInitial[];
}

/** A row starts masked (not replacing) exactly when it carries a mask to show. */
export function initialEnvVarRows(initial: ProjectFormInitial): EnvVarRowState[] {
  return initial.envVars.map((row) => ({
    name: row.name,
    masked: row.masked,
    value: row.value ?? '',
    replacing: row.masked === undefined,
  }));
}

export function initialRepositoryRows(initial: ProjectFormInitial): RepositoryRowState[] {
  return initial.repositories.map((row) => ({ ...row }));
}
