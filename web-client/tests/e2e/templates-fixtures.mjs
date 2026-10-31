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

/* 3.6's own fixtures below — added without changing any value above. */

/**
 * The text `template-diagram.spec.ts` retypes into the editor to prove a redraw. Valid by the
 * stub's validator (no `parallel:`), and shaped to carry every feature the diagram draws:
 * a step that dispatches a harness, a step the file gates with nothing, and a `for_each` with
 * a collapsed call and an item checkpoint inside it.
 */
export const DIAGRAM_EDIT = [
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
  '    uses: agent',
  '    with: { harness: claude }',
  '    gate: liveness',
  '',
  '  - id: draft',
  '    run: "make docs"',
  '',
  '  - id: stories',
  '    for_each: "specs/stories.yaml"',
  '    as: story',
  '    pause_after_item_when: "story.done"',
  '    steps:',
  '      - id: story',
  '        uses: template',
  '        with: { name: helper, version: 1 }',
  '',
].join('\n');

/** The node ids `DIAGRAM_EDIT` draws, in file order. */
export const DIAGRAM_EDIT_NODE_IDS = [
  'checkout',
  'build',
  'draft',
  'stories.story',
  'stories.after',
];

/**
 * Text that does not validate, and that names entirely different steps: what the diagram
 * holds after this is the previous graph's node ids, not this one's.
 */
export const DIAGRAM_INVALID_EDIT = [
  'name: demo',
  'version: 1',
  'parallel: 2',
  'steps:',
  '  - id: nothing-like-the-last-one',
  '    uses: git.sync',
  '    gate: deterministic',
  '',
].join('\n');

/**
 * The shipped `epic@1`, verbatim from `templates/epic.yaml`, so the browser can be shown the
 * one Template the story's first acceptance criterion names. It is the only shipped file with
 * every feature at once — steps before and after a loop, a collapsed call, and an item
 * checkpoint — and `backend-api/tests/e2e/test_template_graph.py` pins the graph the real
 * backend answers for it.
 *
 * Added as a second entry under `EPIC_NAME`, not into `TEMPLATES` above: `GET /api/v1/templates`
 * stays unconditionally empty in the stub (the frozen `shell.spec.ts`), so nothing that reads
 * the list can see this, and `templates.spec.ts` reads `demo` and `helper` only.
 */
export const EPIC_NAME = 'epic';

export const EPIC_V1_YAML = [
  'name: epic',
  'version: 1',
  'description: all stories of one epic on one branch, pushed',
  'inputs:',
  '  branch: { type: string, required: true }',
  'steps:',
  '  - id: checkout',
  '    uses: git.worktree',
  '    with: { base: "main", branch: "{{branch}}" }',
  '    gate: deterministic',
  '',
  '  - id: baseline',
  '    run: "make test"',
  '    gate: deterministic',
  '',
  '  - id: stories',
  '    for_each: "specs/stories.yaml"',
  '    as: story',
  '    pause_after_item_when: "story.done_checkpoint"',
  '    steps:',
  '      - id: story',
  '        uses: template',
  '        with:',
  '          name: story',
  '          version: 1',
  '',
  '  - id: push',
  '    uses: git.push',
  '    with: { branch: "{{branch}}" }',
  '    gate: deterministic',
  '',
  '  - id: link',
  '    uses: pr.link',
  '    with: { branch: "{{branch}}" }',
  '    gate: liveness',
  '',
].join('\n');

/** `epic@1`'s node ids, in file order — the story's first acceptance criterion, as a list. */
export const EPIC_NODE_IDS = [
  'checkout',
  'baseline',
  'stories.story',
  'stories.after',
  'push',
  'link',
];

TEMPLATES[EPIC_NAME] = {
  description: 'all stories of one epic on one branch, pushed',
  versions: {
    1: {
      id: '01a06887-79ab-759b-97a0-71c32ad939e0',
      name: EPIC_NAME,
      version: 1,
      yaml: EPIC_V1_YAML,
      hash: 'e'.repeat(64),
      calls: [],
      called_by: [],
      pinned_by: 0,
      created_at: '2026-09-01T09:00:00Z',
      inputs: [
        { name: 'project', type: 'project', required: true, default: null, values: [] },
        { name: 'repository', type: 'repository', required: true, default: null, values: [] },
        { name: 'base_branch', type: 'string', required: true, default: null, values: [] },
        { name: 'branch', type: 'string', required: true, default: null, values: [] },
        { name: 'spec_folder', type: 'path', required: true, default: null, values: [] },
        { name: 'epic', type: 'item', required: false, default: null, values: [] },
        {
          name: 'harness',
          type: 'enum',
          required: false,
          default: 'claude',
          values: ['claude', 'codex', 'local'],
        },
        { name: 'model', type: 'string', required: false, default: null, values: [] },
      ],
    },
  },
};

/**
 * 4.13's own fixtures below, added the same way 3.6 added `EPIC_NAME` above: a fourth and
 * fifth entry under `TEMPLATES`, so `GET /templates/{name}/versions` answers for real while
 * `GET /api/v1/templates` stays unconditionally empty for the frozen `shell.spec.ts`.
 *
 * These are the two remaining root Templates this epic ships
 * (`templates/initiative.yaml`, `templates/repo-init.yaml`); the third, `epic`, is already
 * above under `EPIC_NAME`. `new-workflow.spec.ts` reads all three, because the New Workflow
 * screen offers all three in its Template dropdown and resolves a version for each.
 */
export const INITIATIVE_NAME = 'initiative';
export const REPO_INIT_NAME = 'repo-init';

TEMPLATES[INITIATIVE_NAME] = {
  description: 'every epic of one initiative, in order, on one repository',
  versions: {
    1: {
      id: '01a06887-79ab-759b-97a0-71c32ad939e1',
      name: INITIATIVE_NAME,
      version: 1,
      yaml: 'name: initiative\nversion: 1\n',
      hash: 'f'.repeat(64),
      calls: [],
      called_by: [],
      pinned_by: 0,
      created_at: '2026-09-01T09:00:00Z',
      inputs: [
        { name: 'project', type: 'project', required: true, default: null, values: [] },
        { name: 'repository', type: 'repository', required: true, default: null, values: [] },
        { name: 'base_branch', type: 'string', required: true, default: null, values: [] },
        { name: 'initiative_folder', type: 'path', required: true, default: null, values: [] },
        {
          name: 'harness',
          type: 'enum',
          required: false,
          default: 'claude',
          values: ['claude', 'codex', 'local'],
        },
        { name: 'model', type: 'string', required: false, default: null, values: [] },
      ],
    },
  },
};

TEMPLATES[REPO_INIT_NAME] = {
  description: 'bootstrap the BMAD method into a repository, opened as a pull request',
  versions: {
    1: {
      id: '01a06887-79ab-759b-97a0-71c32ad939e2',
      name: REPO_INIT_NAME,
      version: 1,
      yaml: 'name: repo-init\nversion: 1\n',
      hash: '0'.repeat(64),
      calls: [],
      called_by: [],
      pinned_by: 0,
      created_at: '2026-09-01T09:00:00Z',
      inputs: [
        { name: 'project', type: 'project', required: true, default: null, values: [] },
        { name: 'repository', type: 'repository', required: true, default: null, values: [] },
        { name: 'base_branch', type: 'string', required: true, default: null, values: [] },
        {
          name: 'harness',
          type: 'enum',
          required: false,
          default: 'claude',
          values: ['claude', 'codex', 'local'],
        },
        { name: 'model', type: 'string', required: false, default: null, values: [] },
      ],
    },
  },
};

/**
 * The two remaining shipped root Templates. `/workflows/new` resolves every name
 * `ROOT_TEMPLATES` offers and reads each one's declared `inputs`, so a name with no fixture
 * here would be dropped from the dropdown. As everywhere in this file the `inputs` are the
 * suite's own data, not a reading of `templates/*.yaml` (hard rule 6).
 */
export const STORY_RUN_NAME = 'story-run';
export const TASK_NAME = 'task';

TEMPLATES[STORY_RUN_NAME] = {
  description: 'one story on its own branch, verified and pushed',
  versions: {
    1: {
      id: '01a06887-79ab-759b-97a0-71c32ad939e3',
      name: STORY_RUN_NAME,
      version: 1,
      yaml: 'name: story-run\nversion: 1\n',
      hash: '1'.repeat(64),
      calls: [],
      called_by: [],
      pinned_by: 0,
      created_at: '2026-09-01T09:00:00Z',
      inputs: [
        { name: 'project', type: 'project', required: true, default: null, values: [] },
        { name: 'repository', type: 'repository', required: true, default: null, values: [] },
        { name: 'base_branch', type: 'string', required: true, default: null, values: [] },
        { name: 'branch', type: 'string', required: true, default: null, values: [] },
        { name: 'spec_folder', type: 'path', required: true, default: null, values: [] },
        { name: 'story_id', type: 'string', required: true, default: null, values: [] },
        { name: 'model_x', type: 'string', required: false, default: null, values: [] },
        { name: 'model_y', type: 'string', required: false, default: 'not-served', values: [] },
        {
          name: 'harness',
          type: 'enum',
          required: false,
          default: 'claude',
          values: ['claude', 'codex', 'local'],
        },
        { name: 'model', type: 'string', required: false, default: null, values: [] },
      ],
    },
  },
};

TEMPLATES[TASK_NAME] = {
  description: 'one issue-sized change through the plan gate',
  versions: {
    1: {
      id: '01a06887-79ab-759b-97a0-71c32ad939e4',
      name: TASK_NAME,
      version: 1,
      yaml: 'name: task\nversion: 1\n',
      hash: '2'.repeat(64),
      calls: [],
      called_by: [],
      pinned_by: 0,
      created_at: '2026-09-01T09:00:00Z',
      inputs: [
        { name: 'project', type: 'project', required: true, default: null, values: [] },
        { name: 'repository', type: 'repository', required: true, default: null, values: [] },
        { name: 'base_branch', type: 'string', required: true, default: null, values: [] },
        { name: 'branch', type: 'string', required: true, default: null, values: [] },
        { name: 'task_id', type: 'string', required: true, default: null, values: [] },
        { name: 'title', type: 'string', required: true, default: null, values: [] },
        { name: 'intent', type: 'string', required: true, default: null, values: [] },
        { name: 'artifacts_dir', type: 'path', required: true, default: null, values: [] },
        {
          name: 'harness',
          type: 'enum',
          required: false,
          default: 'claude',
          values: ['claude', 'codex', 'local'],
        },
        { name: 'model', type: 'string', required: false, default: null, values: [] },
      ],
    },
  },
};
