/**
 * The `ProjectRead` fixtures `stub-backend.mjs` and `projects.spec.ts` share (2.4).
 *
 * Plain JS, not TypeScript: it is imported by the `.mjs` stub server, which runs outside
 * Astro's Vite pipeline and cannot resolve a `.ts` module. `tsconfig.json` already includes
 * `*.mjs`, so `projects.spec.ts` can import the same file with full type-checking.
 *
 * Three Projects cover every row of the intent contract's I/O matrix in one place:
 *
 * - `MIXED` carries one Repository per `clone_check.status` combination the matrix names —
 *   `ok` with a version and a quality gate, `failed` with a hint and output, `ok` with the
 *   `missing` version string and no quality gate, and `pending` with no check run yet — plus
 *   a fifth, `orchestrator-recheck`, that exists solely as the stub's `POST clone-check`
 *   target, so the mutating recheck test never shares a repository with the read-only
 *   assertions the same describe block makes about the others.
 * - `CLEAN` has only `ok` Repositories, for the colour-scan AC.
 * - `NO_REPOS` has none, for the empty-repositories message.
 */
export const MIXED_ID = '00000000-0000-4000-8000-0000000000a1';
export const CLEAN_ID = '00000000-0000-4000-8000-0000000000b1';
export const NO_REPOS_ID = '00000000-0000-4000-8000-0000000000c1';
//: 7.6's own, dedicated fixture — never shared with `MIXED_ID`, the same reasoning
//: `MIXED_RECHECK_REPO_ID` gives its own (`fullyParallel: true`; a fixture whose stub route
//: this story's own spec reads by its `trajectory_count` stays untouched by every other
//: scenario in `projects.spec.ts`, frozen or not).
export const EXPORT_ID = '00000000-0000-4000-8000-0000000000d1';
export const UNKNOWN_ID = '00000000-0000-4000-8000-000000009999';

export const MIXED_OK_REPO_ID = '00000000-0000-4000-8000-0000000000a2';
export const MIXED_FAILED_REPO_ID = '00000000-0000-4000-8000-0000000000a3';
export const MIXED_MISSING_REPO_ID = '00000000-0000-4000-8000-0000000000a4';
export const MIXED_PENDING_REPO_ID = '00000000-0000-4000-8000-0000000000a5';
export const MIXED_RECHECK_REPO_ID = '00000000-0000-4000-8000-0000000000a6';
//: 4.10's own dedicated target — a `POST .../init` fixture, mutated by no other test in
//: this file, the same reasoning `MIXED_RECHECK_REPO_ID` gives `MIXED_FAILED_REPO_ID`.
export const MIXED_INIT_REPO_ID = '00000000-0000-4000-8000-0000000000a7';

/**
 * The repository the stub's `POST clone-check` route flips from `failed` to `ok` — its own,
 * dedicated fixture (`orchestrator-recheck`), never shared with `MIXED_FAILED_REPO_ID`
 * (`orchestrator-web`). `projects.spec.ts` runs under `fullyParallel: true`, and two other
 * tests in the same describe block read `orchestrator-web` expecting it to stay `failed`; if
 * the mutating recheck test and those read-only ones targeted the same repository, their
 * outcome would depend on worker scheduling. Submitting a recheck for `orchestrator-web`
 * itself is still exercised — deliberately, as the "backend refuses the id" case — because it
 * is no longer this constant, so the stub 404s it without mutating anything.
 */
export const RECHECK_REPOSITORY_ID = MIXED_RECHECK_REPO_ID;

const CREATED_AT = '2026-01-05T09:00:00Z';
const UPDATED_AT = '2026-01-06T10:00:00Z';

function repository(overrides) {
  return {
    id: 'repository-id-not-set',
    project_id: 'project-id-not-set',
    slug: 'repo',
    url: 'https://github.com/example/repo.git',
    default_branch: 'main',
    install_command: 'pnpm install',
    quality_gate_command: 'pnpm lint && pnpm test',
    unit_test_command: 'pnpm test',
    test_globs: ['tests/**/*.test.ts'],
    package_manager: 'pnpm',
    clone_check: { status: 'pending', at: null, output: '', bmad_version: null },
    clone_check_lines: [],
    clone_check_hint: '',
    verify_skipped: false,
    created_at: CREATED_AT,
    updated_at: UPDATED_AT,
    ...overrides,
  };
}

function project(overrides) {
  return {
    id: 'project-id-not-set',
    slug: 'project',
    name: 'Project',
    context_text: '',
    context_paths: [],
    env_vars: [],
    log_prompt_content: false,
    repositories: [],
    //: 4.10 — the real contract always carries this key; `[]` reads exactly like the
    //: pre-4.10 fixtures did when `index.astro` falls back on a missing one.
    runs: [],
    //: 7.6 — the real contract always carries this key too; `0` reads exactly like the
    //: pre-7.6 fixtures did when `index.astro` falls back on a missing one (`?? 0`).
    trajectory_count: 0,
    created_at: CREATED_AT,
    updated_at: UPDATED_AT,
    ...overrides,
  };
}

const okRepository = repository({
  id: MIXED_OK_REPO_ID,
  project_id: MIXED_ID,
  slug: 'orchestrator-api',
  quality_gate_command: 'make lint && make test',
  clone_check: {
    status: 'ok',
    at: '2026-09-04T12:00:00Z',
    output: 'cloned ok',
    bmad_version: '6.11.0',
  },
  clone_check_lines: [
    { name: 'clone', status: 'ok', seconds: 4, output: 'Cloning into base...' },
    { name: 'install', status: 'ok', seconds: 11, output: 'added 214 packages' },
  ],
  verify_skipped: false,
});

const failedRepository = repository({
  id: MIXED_FAILED_REPO_ID,
  project_id: MIXED_ID,
  slug: 'orchestrator-web',
  clone_check: {
    status: 'failed',
    at: '2026-09-04T12:05:00Z',
    output: 'fatal: could not read Username for https://github.com: terminal prompts disabled',
    bmad_version: null,
  },
  clone_check_lines: [
    { name: 'clone', status: 'failed', seconds: 2, output: 'fatal: could not read Username' },
  ],
  clone_check_hint: 'add a deploy key or a GITHUB_TOKEN with access to this repository',
  verify_skipped: false,
});

const missingMethodRepository = repository({
  id: MIXED_MISSING_REPO_ID,
  project_id: MIXED_ID,
  slug: 'orchestrator-docs',
  quality_gate_command: '',
  test_globs: [],
  clone_check: {
    status: 'ok',
    at: '2026-09-04T12:10:00Z',
    output: 'cloned ok',
    bmad_version: 'missing',
  },
  clone_check_lines: [{ name: 'clone', status: 'ok', seconds: 3, output: 'Cloning into base...' }],
  verify_skipped: true,
});

const pendingRepository = repository({
  id: MIXED_PENDING_REPO_ID,
  project_id: MIXED_ID,
  slug: 'orchestrator-infra',
  clone_check: { status: 'pending', at: null, output: '', bmad_version: null },
  clone_check_lines: [],
  verify_skipped: false,
});

/** The sole target of the stub's `POST clone-check` route — see `RECHECK_REPOSITORY_ID`. */
const recheckTargetRepository = repository({
  id: MIXED_RECHECK_REPO_ID,
  project_id: MIXED_ID,
  slug: 'orchestrator-recheck',
  clone_check: {
    status: 'failed',
    at: '2026-09-04T12:06:00Z',
    output: 'fatal: authentication failed for https://github.com/example/repo.git',
    bmad_version: null,
  },
  clone_check_lines: [
    { name: 'clone', status: 'failed', seconds: 1, output: 'fatal: authentication failed' },
  ],
  // deliberately distinct from `failedRepository`'s hint text: a Playwright locator by text
  // must resolve to exactly one element, and the two fixtures render on the same page
  clone_check_hint: 'rotate the deploy key configured for this repository',
  verify_skipped: false,
});

/** The sole target of the stub's `POST .../init` route — see `MIXED_INIT_REPO_ID`. Its
 * method is `missing`, exactly the state `Initialise repository` (4.10) offers itself for,
 * and it carries no Run yet: `orchestrator-docs` (`missingMethodRepository` above) stays
 * read-only for every other test in this file. */
const initTargetRepository = repository({
  id: MIXED_INIT_REPO_ID,
  project_id: MIXED_ID,
  slug: 'orchestrator-init',
  quality_gate_command: '',
  test_globs: [],
  clone_check: {
    status: 'ok',
    at: '2026-09-04T12:11:00Z',
    output: 'cloned ok',
    bmad_version: 'missing',
  },
  clone_check_lines: [{ name: 'clone', status: 'ok', seconds: 2, output: 'Cloning into base...' }],
  verify_skipped: true,
});

export const MIXED = project({
  id: MIXED_ID,
  slug: 'mixed-signals',
  name: 'Mixed Signals',
  context_text: 'A BMAD workflow repository and the docs site that tracks it.',
  context_paths: ['docs/architecture.md'],
  env_vars: [{ name: 'NODE_ENV', masked: '****ion' }],
  log_prompt_content: true,
  repositories: [
    okRepository,
    failedRepository,
    missingMethodRepository,
    pendingRepository,
    recheckTargetRepository,
    initTargetRepository,
  ],
  created_at: CREATED_AT,
  updated_at: UPDATED_AT,
});

export const CLEAN = project({
  id: CLEAN_ID,
  slug: 'clean-project',
  name: 'Clean Project',
  context_text: 'Nothing here has ever failed a clone check.',
  log_prompt_content: false,
  repositories: [
    repository({
      id: '00000000-0000-4000-8000-0000000000b2',
      project_id: CLEAN_ID,
      slug: 'clean-api',
      clone_check: {
        status: 'ok',
        at: '2026-09-04T12:00:00Z',
        output: 'cloned ok',
        bmad_version: '6.11.0',
      },
      clone_check_lines: [{ name: 'clone', status: 'ok', seconds: 5, output: 'ok' }],
    }),
    repository({
      id: '00000000-0000-4000-8000-0000000000b3',
      project_id: CLEAN_ID,
      slug: 'clean-web',
      clone_check: {
        status: 'ok',
        at: '2026-09-04T12:00:00Z',
        output: 'cloned ok',
        bmad_version: '6.11.0',
      },
      clone_check_lines: [{ name: 'clone', status: 'ok', seconds: 6, output: 'ok' }],
    }),
  ],
});

export const NO_REPOS = project({
  id: NO_REPOS_ID,
  slug: 'no-repos',
  name: 'No Repositories Yet',
  context_text: '',
  repositories: [],
});

//: 7.6's own fixture (SPEC CAP-6): `trajectory_count` is what the Project screen's *Export
//: trajectories* hint reads, and `stub-backend.mjs`'s new `.../trajectories.jsonl` route
//: answers exactly this many sample lines for this id — the two have to agree by
//: construction, not by a second constant either could drift from.
export const EXPORT_TRAJECTORY_COUNT = 3;

export const EXPORT = project({
  id: EXPORT_ID,
  slug: 'trajectory-source',
  name: 'Trajectory Source',
  context_text: '',
  repositories: [],
  trajectory_count: EXPORT_TRAJECTORY_COUNT,
});

export const PROJECTS_BY_ID = {
  [MIXED_ID]: MIXED,
  [CLEAN_ID]: CLEAN,
  [NO_REPOS_ID]: NO_REPOS,
  [EXPORT_ID]: EXPORT,
};

/**
 * `project-form.spec.ts` (2.5) creates and edits real Projects through the live form, so it
 * needs no stored `ProjectRead` of its own — only the two row values its scenarios name in
 * the story's I/O matrix. `stub-backend.mjs`'s `POST .../clone-check` simulation keys off
 * `UNREACHABLE_REPOSITORY_URL` specifically, matching by substring, to answer `ls-remote
 * failed` for exactly the row that asked for it and `ok` for every other one it creates.
 */
export const UNREACHABLE_REPOSITORY_URL = 'https://github.com/example/unreachable-repo.git';
export const NO_QUALITY_COMMAND_REPOSITORY_URL = 'https://github.com/example/no-quality-gate.git';
