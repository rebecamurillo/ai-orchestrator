/**
 * The Template fixtures `stub-backend.mjs` and `templates.spec.ts` share (3.5).
 *
 * Plain JS, not TypeScript: it is imported by the `.mjs` stub server, which runs outside
 * Astro's Vite pipeline and cannot resolve a `.ts` module — the same reason
 * `projects-fixtures.mjs` is plain JS. `tsconfig.json` already includes `*.mjs`, so
 * `templates.spec.ts` can import the same file with full type-checking.
 *
 * Two Templates cover the story's AC's: `demo` v1 is what `templates.spec.ts` opens, edits
 * (invalid, then valid) and saves as v2; `helper` v1 exists solely so `demo` v1 has a real
 * caller, proving the VERSIONS column's `called by {name}@{v}` fragment end to end. Neither
 * is read from `GET /api/v1/templates` in the live suite — that route answers empty
 * unconditionally (the story's Design Notes) — only from `GET /templates/{name}/versions`
 * and `GET /templates/{name}/{version}`, which this stub answers for real.
 */
export const DEMO_NAME = 'demo';
export const HELPER_NAME = 'helper';
export const UNKNOWN_NAME = 'no-such-template';

const CREATED_AT = '2026-09-01T09:00:00Z';

export const DEMO_V1_YAML = [
  'name: demo',
  'version: 1',
  'description: two steps for the templates screen fixtures',
  'inputs:',
  '  project: { type: project, required: true }',
  'steps:',
  '  - id: checkout',
  '    uses: git.worktree',
  '    with: { base: "main", branch: "chore/demo" }',
  '    gate: deterministic',
  '',
  '  - id: build',
  '    run: "make test"',
  '    gate: liveness',
  '',
].join('\n');

const HELPER_V1_YAML = [
  'name: helper',
  'version: 1',
  'description: calls demo v1',
  'inputs: {}',
  'steps:',
  '  - id: call-demo',
  '    uses: template',
  '    with: { name: demo, version: 1 }',
  '    gate: deterministic',
  '',
].join('\n');

const DEMO_INPUTS = [
  { name: 'project', type: 'project', required: true, default: null, values: [] },
];

/**
 * `name -> { description, versions: { [version]: TemplateVersionOut-shaped } }`. Mutated in
 * place by `stub-backend.mjs`'s save route, so the module the stub imports is a fresh
 * `structuredClone` of this rather than this object itself (`projects-fixtures.mjs`'s same
 * pattern, so a rerun of the suite starts clean).
 */
export const TEMPLATES = {
  [DEMO_NAME]: {
    description: 'two steps for the templates screen fixtures',
    versions: {
      1: {
        name: DEMO_NAME,
        version: 1,
        yaml: DEMO_V1_YAML,
        inputs: DEMO_INPUTS,
        calls: [],
        called_by: [{ name: HELPER_NAME, version: 1 }],
        pinned_by: 0,
        created_at: CREATED_AT,
      },
    },
  },
  [HELPER_NAME]: {
    description: 'calls demo v1',
    versions: {
      1: {
        name: HELPER_NAME,
        version: 1,
        yaml: HELPER_V1_YAML,
        inputs: [],
        calls: [{ name: DEMO_NAME, version: 1 }],
        called_by: [],
        pinned_by: 0,
        created_at: CREATED_AT,
      },
    },
  },
};
