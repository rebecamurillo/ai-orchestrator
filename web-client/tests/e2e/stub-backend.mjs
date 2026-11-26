/**
 * The backend-api stand-in for `make e2e-ui`.
 *
 * The gate exists to prove what web-client does, and running the real stack would couple
 * it to Postgres and to `make e2e-api`. This answers the routes the proxy and Projects
 * specs need and nothing else; `E2E_BACKEND=real` points the same specs at a real
 * backend-api.
 *
 * `/api/v1/echo-auth` deliberately reflects the credential it was sent. Nothing in this
 * system does that, which is exactly why the proxy must be shown to strip it anyway.
 *
 * `GET /api/v1/projects` answers an empty list unconditionally (2.4's design note): the
 * frozen `shell.spec.ts` asserts `NO PROJECTS` at bare `/projects` against this same stub,
 * running under Playwright's `fullyParallel`, so the list route can never answer anything
 * else. The two-item and no-repositories scenarios are proven at `?id=` instead, against
 * `GET /api/v1/projects/{id}`, which does answer the fixed fixtures.
 *
 * 2.5 adds the five route families a real save needs: `POST /projects`, `PUT /projects/{id}`,
 * `POST /projects/{id}/repositories`, `PUT /repositories/{id}`, and a generalised
 * `POST /repositories/{id}/clone-check` that simulates a real check for any Repository this
 * story's own routes create. The one already there (`rerunCloneCheck`, keyed to
 * `RECHECK_REPOSITORY_ID`) is untouched, because `projects.spec.ts` (2.4) depends on every
 * *other* static fixture id still 404ing that route — `STATIC_REPOSITORY_IDS` is the
 * snapshot that keeps the two behaviours apart.
 *
 * 4.10 adds `POST`/`GET /repositories/{id}/init`. There is no engine here to walk a real
 * plan, so `initRepository` simulates the whole Run reaching `done` in the one response —
 * the real timing, queueing and completion hook are `tests/e2e/test_repository_init.py`'s
 * own subject; this stub only has to prove the round trip the page itself drives.
 *
 * 4.13 adds `GET /api/v1/harnesses`, brand new — nothing before it read this route, so
 * unlike the Projects and Templates lists it carries no frozen-empty constraint and answers
 * the three seeded harnesses for real, disabled, exactly as a fresh instance's own
 * `main.seed_harness_table` leaves them (nothing in this epic enables one).
 * `POST /runs/preflight` and `POST /runs` are deliberately not added here:
 * `new-workflow.spec.ts` mocks both with `page.route()`, the same way `template-diagram.
 * spec.ts` mocks `/templates/*graph` and `/validate` — the New Workflow screen's own ACs are
 * about rendering a given response, not about a plan a stub with no engine cannot walk.
 *
 * 4.16 adds `GET /api/v1/queue`, unconditionally empty — the `GET /api/v1/projects` list's
 * own precedent above, needed for the same reason: the frozen `shell.spec.ts` asserts
 * `NO RUNS` at bare `/runs` against this same stub. `runs-queue.spec.ts`'s own real-content
 * scenarios mock this route with `page.route()` instead, `board.spec.ts`'s own precedent.
 *
 * 7.5 adds `GET /api/v1/steps`, unconditionally empty for exactly the same reason one step
 * on: `/runs` now mounts a second island beside the queue, and without this route that
 * island would answer every bare visit with its own failed-fetch readout — a second
 * `fetch-failed` element on a page where `runs-queue.spec.ts` (frozen) asserts on one under
 * Playwright's strict mode. `runs-history.spec.ts`'s real-content scenarios mock it with
 * `page.route()`, the same way.
 *
 * 7.6 adds `GET /api/v1/projects/{id}/trajectories.jsonl`. Unlike every route above, this one
 * is deliberately *not* mocked with `page.route()` in `trajectory-export.spec.ts`: the point
 * of that spec is that a real browser download crosses the real Astro proxy
 * (`src/pages/api/[...path].ts`) with `Content-Disposition` intact, and `page.route()` would
 * intercept the request before the proxy ever saw it. It answers `count` sample ndjson lines
 * for whichever fixture id was asked for, `count` read straight off that fixture's own
 * `trajectory_count` (`EXPORT_TRAJECTORY_COUNT`, `projects-fixtures.mjs`) so the two can never
 * drift apart, and 404s any id `PROJECTS_BY_ID` does not hold.
 */
import { createHash, randomUUID } from 'node:crypto';
import { createServer } from 'node:http';

import { MIXED_ID, PROJECTS_BY_ID, RECHECK_REPOSITORY_ID } from './projects-fixtures.mjs';

const STOPPED_BUILD_RUN = '0193a000-0000-7000-8000-0000000000c4';
import { TEMPLATES } from './templates-fixtures.mjs';

const PORT = Number(process.env.STUB_BACKEND_PORT ?? 8788);
const TOKEN = process.env.ORCHESTRATOR_TOKEN ?? '';

const PROBLEM = 'application/problem+json';
const initiativeMessages = [];
function initiativeTurn(n, status, message, reply) {
  return {
    attempt_id: `0193a000-0000-7000-8000-00000000e0${n}`,
    author: 'operator',
    defects: null,
    ended_at: status === 'done' ? '2026-11-26T21:16:00Z' : null,
    failure_reason: null,
    message,
    model: 'claude-opus-5-5',
    n,
    owner: null,
    reply,
    round: 1,
    run_id: '0193a000-0000-7000-8000-0000000000c1',
    started_at: '2026-11-26T21:15:00Z',
    status,
  };
}
const JSON_TYPE = 'application/json';

/**
 * The in-memory copy `POST .../clone-check` mutates, so a rerun of the suite starts clean.
 * `JSON.parse(JSON.stringify(...))` rather than `structuredClone`: this file's declared
 * globals are deliberately narrow (`eslint.config.js`), and every fixture value is already
 * JSON-safe.
 */
const projects = JSON.parse(JSON.stringify(PROJECTS_BY_ID));

/** Same reasoning as `projects` above: a save (3.5) mutates this in place, so it must be a
 * fresh copy per process rather than the fixture module's own object. */
const templates = JSON.parse(JSON.stringify(TEMPLATES));

/** The three names `main.py`'s `HARNESS_VERSION_SETTINGS` maps, seeded disabled (4.13), each
 * carrying the pin `.env.example` declares for it (`CLAUDE_CODE_VERSION`, `CODEX_VERSION`,
 * `OPENCODE_VERSION`). */
const HARNESSES = [
  {
    name: 'claude',
    enabled: false,
    last_readiness_at: null,
    failing_check: null,
    version_pin: '2.1.258',
  },
  {
    name: 'codex',
    enabled: false,
    last_readiness_at: null,
    failing_check: null,
    version_pin: '0.152.1',
  },
  {
    name: 'local',
    enabled: false,
    last_readiness_at: null,
    failing_check: null,
    version_pin: '1.18.26',
  },
];

/** Every Repository, static fixtures and 2.5's newly created ones alike, keyed by id — the
 * one index `PUT /repositories/{id}` and the clone-check simulation both need, since a
 * repository route carries no `project_id` of its own. */
const repositoriesById = new Map();
for (const project of Object.values(projects)) {
  for (const repository of project.repositories) repositoriesById.set(repository.id, repository);
}

/** The ids that existed before any request landed — `projects.spec.ts` (2.4) depends on
 * every one of these except `RECHECK_REPOSITORY_ID` still 404ing the clone-check route. */
const STATIC_REPOSITORY_IDS = new Set(repositoriesById.keys());

/** The real, per-Project value behind each masked `env_vars[]` entry, so a `PUT` that omits
 * `value` can keep it and so the mask can be recomputed from whatever replaces it. Never
 * serialised — only `applyEnvVars`'s return value (`{name, masked}`) leaves this module. */
const envVarValues = new Map();
for (const project of Object.values(projects)) {
  for (const variable of project.env_vars) {
    envVarValues.set(`${project.id}::${variable.name}`, 'stored-value');
  }
}

function slugify(text) {
  const slug = text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug.length > 0 ? slug : 'unnamed';
}

function repositorySlug(url) {
  const last =
    url
      .replace(/\.git$/, '')
      .split('/')
      .pop() ?? 'repo';
  return slugify(last);
}

function maskValue(value) {
  return `****${value.slice(-4)}`;
}

/** `[{name, value?}]` -> `[{name, masked}]`, keeping a value that was left out (2.1's rule,
 * exercised end to end here rather than only in the backend this stub stands in for). */
function applyEnvVars(projectId, incoming) {
  return incoming.map((entry) => {
    const key = `${projectId}::${entry.name}`;
    if (typeof entry.value === 'string') envVarValues.set(key, entry.value);
    return { name: entry.name, masked: maskValue(envVarValues.get(key) ?? '') };
  });
}

function createProject(body) {
  const now = new Date().toISOString();
  const id = randomUUID();
  const project = {
    id,
    slug: slugify(body.name ?? ''),
    name: body.name,
    context_text: body.context_text ?? '',
    context_paths: body.context_paths ?? [],
    env_vars: [],
    log_prompt_content: body.log_prompt_content ?? false,
    repositories: [],
    runs: [],
    created_at: now,
    updated_at: now,
  };
  project.env_vars = applyEnvVars(id, body.env_vars ?? []);
  projects[id] = project;
  return project;
}

function updateProject(id, body) {
  const project = projects[id];
  if (!project) return null;
  project.name = body.name;
  project.context_text = body.context_text ?? '';
  project.context_paths = body.context_paths ?? [];
  if (typeof body.log_prompt_content === 'boolean')
    project.log_prompt_content = body.log_prompt_content;
  project.env_vars = applyEnvVars(id, body.env_vars ?? []);
  project.updated_at = new Date().toISOString();
  return project;
}

function repositoryFields(body) {
  return {
    url: body.url,
    default_branch: body.default_branch,
    install_command: body.install_command ?? '',
    quality_gate_command: body.quality_gate_command ?? '',
    unit_test_command: body.unit_test_command ?? '',
    test_globs: body.test_globs ?? [],
    package_manager: body.package_manager ?? 'other',
  };
}

function addRepository(projectId, body) {
  const project = projects[projectId];
  if (!project) return null;
  const now = new Date().toISOString();
  const fields = repositoryFields(body);
  const repository = {
    id: randomUUID(),
    project_id: projectId,
    slug: repositorySlug(fields.url),
    ...fields,
    clone_check: { status: 'pending', at: null, output: '', bmad_version: null },
    clone_check_lines: [],
    clone_check_hint: '',
    verify_skipped: fields.quality_gate_command.trim().length === 0,
    created_at: now,
    updated_at: now,
  };
  project.repositories.push(repository);
  repositoriesById.set(repository.id, repository);
  return repository;
}

function updateRepository(repositoryId, body) {
  const repository = repositoriesById.get(repositoryId);
  if (!repository) return null;
  Object.assign(repository, repositoryFields(body));
  repository.verify_skipped = repository.quality_gate_command.trim().length === 0;
  repository.updated_at = new Date().toISOString();
  return repository;
}

/** The four named lines a real check reports, in the fixed order the backend runs them
 * (`domain/entities/repository.py`'s `LINE_*` constants). */
function okCloneCheckLines() {
  return [
    { name: 'ls-remote', status: 'ok', seconds: 0.2, output: 'ok' },
    { name: 'clone', status: 'ok', seconds: 1.5, output: 'Cloning into base...' },
    { name: 'default branch', status: 'ok', seconds: 0.1, output: 'ok' },
    { name: 'method version', status: 'ok', seconds: 0.1, output: 'ok' },
  ];
}

/** `UNREACHABLE_REPOSITORY_URL` (`projects-fixtures.mjs`) is the one substring this stub
 * treats as a token the instance cannot reach — every other url this route creates checks
 * `ok`, matching the story's "a failing check never fails the save" (2.3). */
function simulateCloneCheck(repository) {
  const now = new Date().toISOString();
  if (repository.url.includes('unreachable')) {
    const output = `fatal: could not read Username for '${repository.url}': terminal prompts disabled`;
    repository.clone_check = { status: 'failed', at: now, output, bmad_version: null };
    repository.clone_check_lines = [{ name: 'ls-remote', status: 'failed', seconds: 0.3, output }];
    repository.clone_check_hint =
      'add a deploy key or a GITHUB_TOKEN with access to this repository';
  } else {
    repository.clone_check = { status: 'ok', at: now, output: 'cloned ok', bmad_version: '6.11.0' };
    repository.clone_check_lines = okCloneCheckLines();
    repository.clone_check_hint = '';
  }
  return {
    status: repository.clone_check.status,
    at: repository.clone_check.at,
    output: repository.clone_check.output,
    bmad_version: repository.clone_check.bmad_version,
    lines: repository.clone_check_lines,
    hint: repository.clone_check_hint,
  };
}

const packageOverrides = {};

function readJsonBody(request) {
  return new Promise((resolve, reject) => {
    let data = '';
    request.on('data', (chunk) => {
      data += chunk;
    });
    request.on('end', () => {
      try {
        resolve(data.length > 0 ? JSON.parse(data) : {});
      } catch (error) {
        reject(error);
      }
    });
    request.on('error', reject);
  });
}

function send(response, status, type, body, headers = {}) {
  response.writeHead(status, { 'Content-Type': type, ...headers });
  response.end(body);
}

function notFound(response, title) {
  send(response, 404, PROBLEM, JSON.stringify({ type: 'about:blank', title, status: 404 }));
}

/** One `trajectories.jsonl` line (SPEC CAP-6), field-complete but content-arbitrary — the
 * download scenario reads its filename and its line count, not what any field says. */
function sampleTrajectoryLine(project, n) {
  return {
    id: randomUUID(),
    run_id: randomUUID(),
    project_id: project.id,
    repository_id: randomUUID(),
    story_id: `${n}-1`,
    epic_index: n,
    frame: `stories[${n}]`,
    harness: 'claude',
    model: 'sonnet',
    attempts: [],
    gate_results: {
      build: 'liveness',
      verify: 'done',
      commit_guard: 'done',
      protected_paths: { hits: [], accepted: [] },
    },
    cost_usd: '0.000000',
    tokens_in: 0,
    tokens_out: 0,
    wall_clock_seconds: 0,
    story_file: '',
    start_sha: null,
    end_sha: null,
    human_actions: [],
    recorded_at: '2026-09-10T12:00:00Z',
  };
}

/** Flip the recheck target's stored result from `failed` to `ok`, in place. */
function rerunCloneCheck(repositoryId) {
  if (repositoryId !== RECHECK_REPOSITORY_ID) return null;

  for (const project of Object.values(projects)) {
    const repository = project.repositories.find((candidate) => candidate.id === repositoryId);
    if (!repository) continue;

    repository.clone_check = {
      status: 'ok',
      at: new Date().toISOString(),
      output: 'cloned ok',
      bmad_version: '6.11.0',
    };
    repository.clone_check_lines = [{ name: 'clone', status: 'ok', seconds: 3, output: 'ok' }];
    repository.clone_check_hint = '';
    return {
      status: repository.clone_check.status,
      at: repository.clone_check.at,
      output: repository.clone_check.output,
      bmad_version: repository.clone_check.bmad_version,
      lines: repository.clone_check_lines,
      hint: repository.clone_check_hint,
    };
  }
  return null;
}

//: The tokens `handle_signal`/`run_admitted_signals` (4.9) leave a Run in once it stops
//: changing — mirrored here rather than imported, since this file runs outside the backend.
const REPO_INIT_TERMINAL_TOKENS = new Set(['DON', 'ERR', 'CAN']);

/**
 * `POST /repositories/{id}/init` (4.10): finds the Project a Repository belongs to, refuses
 * the same two ways the real endpoint does, and otherwise simulates the whole Run reaching
 * `done` at once — pushing one entry onto that Project's own `runs[]`. There is no engine
 * here to walk a real plan: the real timing, queueing and completion hook are
 * `tests/e2e/test_repository_init.py`'s own subject; this stub only has to prove the round
 * trip the page itself drives.
 */
function initRepository(repositoryId) {
  const repository = repositoriesById.get(repositoryId);
  if (!repository) return { status: 404, title: 'no Repository has that id' };
  const project = Object.values(projects).find((candidate) =>
    candidate.repositories.some((candidateRepository) => candidateRepository.id === repositoryId),
  );

  if (repository.clone_check.status === 'failed') {
    return {
      status: 409,
      title: 'conflict',
      detail: 'clone check failed: run the clone check again before initialising',
    };
  }
  const running = (project.runs ?? []).find(
    (run) =>
      run.repository_id === repositoryId &&
      run.is_init === true &&
      !REPO_INIT_TERMINAL_TOKENS.has(run.token),
  );
  if (running) {
    return {
      status: 409,
      title: 'conflict',
      detail: `initialisation already running: ${running.id}`,
    };
  }

  const now = new Date().toISOString();
  const runId = randomUUID();
  const compareUrl = `https://github.com/example/${repository.slug}/compare/${repository.default_branch}...chore/bmad-init`;
  project.runs = [
    {
      id: runId,
      token: 'DON',
      template: 'repo-init@1',
      // the server marks the Run it dispatched from INIT_TEMPLATE (`ProjectRunOut.is_init`);
      // the page reads that flag, never the label (Operator decision 2026-09-30)
      is_init: true,
      branch: repository.default_branch,
      repository_id: repositoryId,
      current_step_label: 'link',
      reason: '',
      compare_urls: [compareUrl],
      created_at: now,
    },
    ...(project.runs ?? []),
  ];

  return {
    status: 201,
    body: {
      run: {
        id: runId,
        status: 'done',
        template: 'repo-init',
        version: 1,
        project: project.id,
        repository: repositoryId,
        branch: repository.default_branch,
        budget_usd: '0',
        spend_usd: '0',
        plan_ref: null,
        created_at: now,
        admitted_signals: [],
      },
      starts_now: true,
      waiting: '',
    },
  };
}

/** 3.5's own routes below — every route the four `/templates` endpoints `templates.spec.ts`
 * needs, added without touching any branch above. */

function sha256Hex(text) {
  return createHash('sha256').update(text).digest('hex');
}

/** A stand-in for the real validator (AD-15 lives in backend-api, never reimplemented here):
 * `parallel:` is treated as reserved wherever it appears, and a step (a `- id:` line) with
 * no `gate:` anywhere in its own block is reported `unvalidated · steps.{id}` — exactly the
 * two facts the story's AC2 needs, computed the same way `src/lib/editor/yamlEditor.ts`
 * finds a step's own range: a line-and-indentation scan, never a YAML parse. */
function validateYamlText(text) {
  const lines = text.split('\n');
  const errors = [];
  lines.forEach((line, index) => {
    if (/^\s*parallel:/.test(line)) {
      errors.push({
        line: index + 1,
        path: null,
        template: null,
        version: null,
        reason: 'parallel is reserved',
      });
    }
  });

  const unvalidated = [];
  const stepStarts = [];
  lines.forEach((line, index) => {
    const match = line.match(/^(\s*)-\s+id:\s*(\S+)/);
    if (match) stepStarts.push({ index, indent: match[1].length, id: match[2] });
  });
  stepStarts.forEach((step) => {
    let end = lines.length;
    for (let i = step.index + 1; i < lines.length; i++) {
      const candidate = lines[i];
      if (candidate.trim().length === 0) continue;
      const spaces = candidate.match(/^ */)[0].length;
      if (spaces <= step.indent) {
        end = i;
        break;
      }
    }
    const block = lines.slice(step.index, end).join('\n');
    if (!/\bgate:\s*\S/.test(block)) unvalidated.push(`steps.${step.id}`);
  });

  return { errors, unvalidated };
}

/** `version` must read `max(existing) + 1` (AD-15) — the same rule the real backend applies,
 * so `rewriteVersionLine` (`src/lib/editor/yamlEditor.ts`) is exercised against a stub that
 * actually checks its work rather than accepting anything posted. */
function saveTemplateVersion(name, yamlText) {
  const template = templates[name];
  if (!template)
    return {
      status: 404,
      body: { type: 'about:blank', title: 'no Template has that name', status: 404 },
    };

  const { errors } = validateYamlText(yamlText);
  if (errors.length > 0) {
    return {
      status: 422,
      body: {
        type: 'about:blank',
        title: 'invalid template',
        status: 422,
        detail: 'validation failed',
        errors,
      },
    };
  }

  const versionNumbers = Object.keys(template.versions).map(Number);
  const maxVersion = Math.max(...versionNumbers);
  const versionMatch = yamlText.match(/^version:\s*(\d+)/m);
  const declaredVersion = versionMatch ? Number(versionMatch[1]) : null;
  if (declaredVersion !== maxVersion + 1) {
    return {
      status: 422,
      body: {
        type: 'about:blank',
        title: 'invalid template',
        status: 422,
        detail: 'version must be the next one',
        errors: [
          {
            line: null,
            path: 'yaml',
            template: name,
            version: declaredVersion,
            reason: `version must be ${maxVersion + 1}`,
          },
        ],
      },
    };
  }

  const saved = {
    name,
    version: declaredVersion,
    yaml: yamlText,
    hash: sha256Hex(yamlText),
    calls: [],
    called_by: [],
    pinned_by: 0,
    inputs: template.versions[maxVersion].inputs,
    created_at: new Date().toISOString(),
  };
  template.versions[declaredVersion] = saved;
  return { status: 201, body: saved };
}

/** 3.6's own routes below — the two `/graph` endpoints the Templates screen's diagram needs,
 * added without touching any branch above. */

/** The block a `- id:` line owns: every following line indented deeper than it is. */
function stepBlock(lines, step) {
  let end = lines.length;
  for (let i = step.index + 1; i < lines.length; i++) {
    if (lines[i].trim().length === 0) continue;
    if (lines[i].match(/^ */)[0].length <= step.indent) {
      end = i;
      break;
    }
  }
  return { end, text: lines.slice(step.index, end).join('\n') };
}

/** One step as one node, the way `application/graph.py` shapes it (never re-derived: this
 * stub stands in for the backend, and the shapes it answers are that module's, restated
 * lexically for the fixtures this suite types in). */
function nodeFromStep(id, block) {
  const uses = block.match(/^\s+uses:\s*(\S+)/m);
  // `run:` is sugar for the `shell` kind, and a step declares one of the two
  const kind = uses ? uses[1] : 'shell';
  if (kind === 'template') {
    const name = block.match(/name:\s*([\w.-]+)/);
    const version = block.match(/version:\s*(\d+)/);
    const callee = { name: name ? name[1] : 'unknown', version: version ? Number(version[1]) : 1 };
    return {
      id,
      kind: 'template',
      label: `${callee.name}@${callee.version}`,
      gate: null,
      agent: false,
      human: false,
      call: callee,
    };
  }
  const declared = block.match(/^\s+gate:\s*(\S+)/m);
  const gate = declared ? declared[1] : 'unvalidated';
  return {
    id,
    kind,
    label: id.split('.').pop(),
    gate,
    agent: kind === 'agent',
    human: gate === 'human' || kind === 'checkpoint',
    call: null,
  };
}

/** The synthetic stop a `pause_*_item_when` declares: one per item, inside the loop's box. */
function itemCheckpoint(loopId, position) {
  return {
    id: `${loopId}.${position}`,
    kind: 'checkpoint',
    label: position,
    gate: 'human',
    agent: false,
    human: true,
    call: null,
  };
}

/** `{nodes, edges, groups}` from Template text, by the same line-and-indentation scan
 * `validateYamlText` uses — never a YAML parse, and never in the browser (AD-15: the real
 * shaping is `application/graph.py`, which this stub stands in for). */
function graphFromYaml(text) {
  const lines = text.split('\n');
  const steps = [];
  lines.forEach((line, index) => {
    const match = line.match(/^(\s*)-\s+id:\s*(\S+)/);
    if (match) steps.push({ index, indent: match[1].length, id: match[2] });
  });
  if (steps.length === 0) return { nodes: [], edges: [], groups: [] };

  const top = Math.min(...steps.map((step) => step.indent));
  const nodes = [];
  const edges = [];
  const groups = [];
  let previous = null;

  for (const step of steps.filter((candidate) => candidate.indent === top)) {
    const { end, text: block } = stepBlock(lines, step);
    const frame = [];
    if (/^\s+for_each:/m.test(block)) {
      if (/^\s+pause_before_item_when:/m.test(block)) frame.push(itemCheckpoint(step.id, 'before'));
      for (const inner of steps.filter(
        (candidate) =>
          candidate.index > step.index && candidate.index < end && candidate.indent > top,
      )) {
        frame.push(nodeFromStep(`${step.id}.${inner.id}`, stepBlock(lines, inner).text));
      }
      if (/^\s+pause_after_item_when:/m.test(block)) frame.push(itemCheckpoint(step.id, 'after'));
      groups.push({
        id: step.id,
        label: step.id,
        kind: 'for_each',
        members: frame.map((node) => node.id),
      });
    } else {
      frame.push(nodeFromStep(step.id, block));
    }
    if (frame.length === 0) continue;
    if (previous !== null) edges.push({ from: previous, to: frame[0].id });
    for (let i = 1; i < frame.length; i++) edges.push({ from: frame[i - 1].id, to: frame[i].id });
    nodes.push(...frame);
    previous = frame[frame.length - 1].id;
  }

  return { nodes, edges, groups };
}

createServer(async (request, response) => {
  const authorized = request.headers.authorization === `Bearer ${TOKEN}`;
  const { pathname } = new URL(request.url, `http://127.0.0.1:${PORT}`);

  if (!authorized) {
    const body = JSON.stringify({ type: 'about:blank', title: 'unauthorized', status: 401 });
    send(response, 401, PROBLEM, body, { 'WWW-Authenticate': 'Bearer' });
    return;
  }
  if (pathname === '/api/v1/ping') {
    send(response, 200, JSON_TYPE, JSON.stringify({ pong: true }));
    return;
  }
  if (pathname === '/api/v1/echo-auth') {
    send(response, 200, JSON_TYPE, JSON.stringify({ echoed: true }), {
      Authorization: request.headers.authorization,
      'X-Echoed-Credential': request.headers.authorization,
    });
    return;
  }
  if (pathname === '/api/v1/harnesses' && request.method === 'GET') {
    send(response, 200, JSON_TYPE, JSON.stringify({ items: HARNESSES, next_cursor: null }));
    return;
  }
  if (pathname === '/api/v1/queue' && request.method === 'GET') {
    // forced empty unconditionally, `GET /api/v1/projects`'s own precedent above: the
    // frozen `shell.spec.ts` asserts `NO RUNS` at bare `/runs` against this same,
    // `fullyParallel` stub; every real-content scenario (4.16) mocks this route with
    // `page.route()` instead, `board.spec.ts`'s own precedent for `GET /runs?view=board`
    send(
      response,
      200,
      JSON_TYPE,
      JSON.stringify({ items: [], next_cursor: null, max_active_runs: 2 }),
    );
    return;
  }
  if (pathname === '/api/v1/steps' && request.method === 'GET') {
    // forced empty unconditionally, `GET /api/v1/queue`'s own precedent directly above
    send(response, 200, JSON_TYPE, JSON.stringify({ items: [], next_cursor: null }));
    return;
  }
  if (pathname === '/api/v1/initiatives' && request.method === 'GET') {
    send(
      response,
      200,
      JSON_TYPE,
      JSON.stringify({
        columns: [
          { workflow: 'spec', type: 'interactive' },
          { workflow: 'build', type: 'auto' },
        ],
        counts: { ongoing: 1, need_you: 1, cancelled: 0, oldest_wait_at: new Date().toISOString() },
        items: [
          {
            attention: 'your_turn',
            id: '0193a000-0000-7000-8000-000000000001',
            line: 'ux · your turn · 14 turns',
            name: 'Initiative steps',
            position: 0,
            progress: '1 of 3 steps',
            project_id: '0193a000-0000-7000-8000-000000000002',
            project_name: 'Orchestrator',
            reason: '',
            repo_tag: ['ai-orchestrator'],
            repository_id: '0193a000-0000-7000-8000-000000000003',
            slug: 'initiative-steps',
            status: 'waiting for her',
            step: 'ux',
            updated_at: new Date().toISOString(),
            workflow: 'spec',
            workflow_count: 2,
            workflows: [
              { workflow: 'spec', type: 'interactive', state: 'ongoing' },
              { workflow: 'build', type: 'auto', state: null },
            ],
          },
        ],
        next_cursor: null,
      }),
    );
    return;
  }
  if (/^\/api\/v1\/runs\/[^/]+\/session\/messages$/.test(pathname) && request.method === 'POST') {
    let raw = '';
    request.on('data', (chunk) => (raw += chunk));
    request.on('end', () => {
      const { text } = JSON.parse(raw || '{}');
      initiativeMessages.push(text);
      send(
        response,
        202,
        JSON_TYPE,
        JSON.stringify({
          attempt_id: '0193a000-0000-7000-8000-0000000000d1',
          cost_usd: null,
          ended_at: null,
          exit_code: null,
          message: text,
          reply: '',
          started_at: null,
          status: 'queued',
          turn: 15 + initiativeMessages.length,
        }),
      );
    });
    return;
  }
  // Story 11.5: the answers to the stops. Placed before the broader initiative branch.
  if (/^\/api\/v1\/runs\/[^/]+\/session\/retry$/.test(pathname) && request.method === 'POST') {
    send(
      response,
      201,
      JSON_TYPE,
      JSON.stringify({
        attempt_id: '0193a000-0000-7000-8000-0000000000d2',
        cost_usd: null,
        ended_at: null,
        exit_code: null,
        message: '',
        reply: '',
        started_at: null,
        status: 'queued',
        turn: 15,
      }),
    );
    return;
  }
  if (/^\/api\/v1\/initiatives\/[^/]+\/reopen$/.test(pathname) && request.method === 'POST') {
    send(
      response,
      201,
      JSON_TYPE,
      JSON.stringify({ round: 2, run_id: '0193a000-0000-7000-8000-0000000000c1', step: 'ux' }),
    );
    return;
  }
  const runDefaultsMatch = pathname.match(/^\/api\/v1\/projects\/([^/]+)\/run-defaults$/);
  if (runDefaultsMatch && request.method === 'PUT') {
    const project = projects[runDefaultsMatch[1]];
    if (!project) {
      notFound(response, 'Project not found');
      return;
    }
    await readJsonBody(request);
    send(response, 200, JSON_TYPE, JSON.stringify(project));
    return;
  }
  // start-next and cancel answer the same detail body as the GET (story 11.4).
  if (
    (/^\/api\/v1\/initiatives\/[^/]+$/.test(pathname) && request.method === 'GET') ||
    (/^\/api\/v1\/initiatives\/[^/]+\/(start-next|cancel)$/.test(pathname) &&
      request.method === 'POST')
  ) {
    const ids = ['product', 'arch', 'ux', 'plan', 'review', 'close'];
    const steps = ids.map((id, i) => ({
      id,
      kind: 'conversation',
      status: i < 2 ? 'done' : i === 2 ? 'running' : 'planned',
      token: i < 2 ? 'DON' : i === 2 ? 'RUN' : 'QUE',
      line: i === 2 ? 'your turn · 14 turns' : '',
      agent: 'analyst',
      turns: [],
      files: [],
      files_state: i < 2 ? 'done' : i === 2 ? 'open' : 'to come',
      conflict_files: [],
      ...(id === 'ux'
        ? {
            park_kind: 'conversation',
            park_seq: 7,
            run_id: '0193a000-0000-7000-8000-0000000000c1',
            file: 'DESIGN.md',
            files: [
              {
                path: 'DESIGN.md',
                changed: true,
                draft: true,
                run_id: '0193a000-0000-7000-8000-0000000000c1',
                time: '2026-11-22T21:30:00Z',
              },
            ],
            harness: 'claude',
            model: 'claude-opus-5-5',
            turns: [
              initiativeTurn(14, 'done', 'Which colours?', 'Warm ones.'),
              initiativeTurn(15, 'running', 'And the fonts?', ''),
              ...initiativeMessages.map((text, k) => initiativeTurn(16 + k, 'queued', text, '')),
            ],
          }
        : {}),
    }));
    const detailId = pathname.split('/').pop();
    const mergeStop = detailId === '0193a000-0000-7000-8000-0000000000f2';
    const budgetStop = detailId === '0193a000-0000-7000-8000-0000000000f3';
    const buildStop = detailId === '0193a000-0000-7000-8000-0000000000f4';
    if (mergeStop) {
      steps.push({
        id: 'merge',
        kind: 'automatic',
        status: 'waiting for her',
        token: 'BLK',
        line: 'merge conflict',
        agent: 'merge agent',
        turns: [],
        files: [],
        files_state: 'open',
        conflict_files: ['planning/decision-log.md'],
        park_kind: 'merge_conflict',
        park_seq: 8,
        run_id: '0193a000-0000-7000-8000-0000000000c2',
      });
      for (const s of steps) {
        if (s.id === 'ux') Object.assign(s, { status: 'done', token: 'DON', park_kind: null });
      }
    }
    const body = {
      id: detailId,
      slug: 'familio-dessin-v2',
      name: 'Familio Dessin v2',
      status: 'running',
      workflow: 'spec',
      step: 'ux',
      current_step: 'ux',
      current_position: 1,
      workflow_count: 2,
      attention: 'your_turn',
      reason: '',
      hub: { id: '0193a000-0000-7000-8000-0000000000a1', slug: 'hub-repo' },
      folder: 'initiatives/familio-dessin-v2',
      package: 'orchestrator-default',
      sequence_fixed_at: '2026-11-20T10:00:00Z',
      created_at: '2026-11-19T09:00:00Z',
      project: { id: '0193a000-0000-7000-8000-0000000000b1', name: 'Familio' },
      project_id: '0193a000-0000-7000-8000-0000000000b1',
      project_name: 'Familio',
      repo_tag: ['familio-web'],
      runs: [],
      sessions: [
        {
          workflow: 'spec',
          step: 'product',
          kind: 'session',
          id: '0193a1b2-0000-7000-8000-0000000011ab',
          round: 1,
          state: 'closed',
        },
        {
          workflow: 'spec',
          step: 'ux',
          kind: 'session',
          id: '0193c3d4-0000-7000-8000-000000007f21',
          round: 1,
          state: 'open',
        },
      ],
      workflows: [
        {
          workflow: 'spec',
          position: 1,
          type: 'interactive',
          template: 'initiative-hub',
          version: 1,
          run_id: null,
          status: null,
          token: 'RUN',
          line: 'ux · your turn',
          steps,
          files: [],
        },
        {
          workflow: 'build',
          position: 2,
          type: 'auto',
          template: 'initiative-hub-epic',
          version: 1,
          run_id: null,
          status: null,
          token: null,
          line: 'starts when spec is done',
          steps: [],
          files: [],
        },
      ],
    };
    if (mergeStop) {
      Object.assign(body, {
        status: 'waiting for her',
        step: 'merge',
        current_step: 'merge',
        attention: 'blocked',
      });
    }
    if (buildStop) {
      const agents = ['intake-router', 'product-lead', 'ux-lead', 'tech-lead'];
      Object.assign(body, {
        status: 'waiting for her',
        step: 'build',
        current_step: null,
        current_position: 2,
        attention: 'blocked',
        reason: 'verify failed: make test exited 2',
        round: 1,
        owners: [],
        runs: [
          {
            id: STOPPED_BUILD_RUN,
            status: 'needs_you',
            created_at: '2026-11-22T10:00:00Z',
            position: 2,
            round: 1,
            template_name: 'initiative-hub-epic',
            template_version: 1,
          },
        ],
      });
      body.workflows[0].steps = ['intake', 'product', 'ux', 'tech'].map((id, i) => ({
        id,
        kind: 'conversation',
        status: 'done',
        token: 'DON',
        line: '',
        number: `1.${i + 1}`,
        agent: agents[i],
        turns: [],
        files: [],
        files_state: 'open',
        park_kind: null,
        reopened_after: null,
      }));
      body.workflows[0].status = 'done';
      body.workflows[0].token = 'DON';
      Object.assign(body.workflows[1], {
        run_id: STOPPED_BUILD_RUN,
        status: 'needs_you',
        token: 'BLK',
        line: 'verify failed: make test exited 2',
      });
    }
    if (budgetStop) {
      Object.assign(body, {
        status: 'waiting for her',
        step: 'build',
        current_step: null,
        current_position: 2,
        attention: 'blocked',
        reason: 'no project budget',
        project: { id: MIXED_ID, name: 'Familio' },
        project_id: MIXED_ID,
      });
      body.workflows[0].run_id = '0193a000-0000-7000-8000-0000000000c3';
      body.workflows[0].status = 'done';
      body.workflows[0].token = 'DON';
      body.workflows[0].steps = body.workflows[0].steps.map((s) => ({
        ...s,
        status: 'done',
        token: 'DON',
        park_kind: null,
      }));
      body.sessions = [];
    }
    send(response, 200, JSON_TYPE, JSON.stringify(body));
    return;
  }
  if (pathname === '/api/v1/initiatives' && request.method === 'POST') {
    send(
      response,
      201,
      JSON_TYPE,
      JSON.stringify({ id: '0193a000-0000-7000-8000-0000000000f1', slug: 'new-initiative' }),
    );
    return;
  }
  const packageMatch = /^\/api\/v1\/projects\/([^/]+)\/package$/.exec(pathname);
  if (packageMatch && request.method === 'PUT') {
    const body = await readJsonBody(request);
    if (!projects[packageMatch[1]]) {
      send(
        response,
        404,
        'application/problem+json',
        JSON.stringify({ type: 'about:blank', title: 'Not Found', status: 404 }),
      );
      return;
    }
    packageOverrides[packageMatch[1]] = {
      path: body.path,
      ref: body.ref,
      repository_id: body.repository_id,
    };
    send(response, 200, JSON_TYPE, JSON.stringify({ project_id: packageMatch[1], ...body }));
    return;
  }
  if (packageMatch && request.method === 'DELETE') {
    if (packageMatch[1] === MIXED_ID) {
      send(
        response,
        409,
        'application/problem+json',
        JSON.stringify({
          type: 'about:blank',
          title: 'Conflict',
          status: 409,
          detail:
            'refused: 2 open initiatives use this package — familio-dessin-v2, familio-chores-v3',
        }),
      );
      return;
    }
    response.writeHead(204);
    response.end();
    return;
  }
  const folderMatch = /^\/api\/v1\/repositories\/([^/]+)\/initiative-folder$/.exec(pathname);
  if (folderMatch && request.method === 'PUT') {
    const body = await readJsonBody(request);
    for (const project of Object.values(projects)) {
      const repository = project.repositories.find((r) => r.id === folderMatch[1]);
      if (repository) {
        repository.initiative_folder = body.initiative_folder;
        send(response, 200, JSON_TYPE, JSON.stringify(repository));
        return;
      }
    }
    send(
      response,
      404,
      'application/problem+json',
      JSON.stringify({ type: 'about:blank', title: 'Not Found', status: 404 }),
    );
    return;
  }
  if (packageMatch && request.method === 'GET') {
    if (!projects[packageMatch[1]]) {
      send(
        response,
        404,
        'application/problem+json',
        JSON.stringify({ type: 'about:blank', title: 'Not Found', status: 404 }),
      );
      return;
    }
    const step = (id, kind, persona, writes) => ({
      file: null,
      id,
      kind,
      persona,
      skill: null,
      writes,
    });
    send(
      response,
      200,
      JSON_TYPE,
      JSON.stringify({
        gate: {},
        id: '0193a000-0000-7000-8000-0000000000f2',
        installed_at: '2026-11-20T10:00:00Z',
        name: 'stub-package',
        path: 'package',
        project_id: packageMatch[1],
        ref: 'main',
        ...packageOverrides[packageMatch[1]],
        repository: {
          default_branch: 'main',
          id: '0193a000-0000-7000-8000-0000000000f3',
          initiative_folder: 'initiatives',
          slug: 'hub',
        },
        repository_id: '0193a000-0000-7000-8000-0000000000f3',
        sequence: [
          {
            shown_as: 'workflow',
            steps: [
              step('brief', 'conversation', 'analyst', ['SPEC.md']),
              step('check', 'automatic', 'reviewer', []),
            ],
            template: 'initiative-hub',
            type: 'interactive',
            version: 1,
            workflow: 'spec',
          },
          {
            shown_as: 'step',
            steps: [step('merge', 'automatic', 'merger', [])],
            template: 'initiative-hub-merge',
            type: 'auto',
            version: 1,
            workflow: 'merge',
          },
          {
            shown_as: 'workflow',
            steps: [],
            template: 'staged-initiative-hub',
            type: 'auto',
            version: 4,
            workflow: 'build',
          },
        ],
        sha: 'abc123',
        status_map: {},
      }),
    );
    return;
  }
  if (pathname === '/api/v1/projects' && request.method === 'GET') {
    send(response, 200, JSON_TYPE, JSON.stringify({ items: [], next_cursor: null }));
    return;
  }
  if (pathname === '/api/v1/projects' && request.method === 'POST') {
    const project = createProject(await readJsonBody(request));
    send(response, 201, JSON_TYPE, JSON.stringify(project));
    return;
  }
  if (/^\/api\/v1\/projects\/[^/]+\/initiatives$/.test(pathname) && request.method === 'GET') {
    send(
      response,
      200,
      JSON_TYPE,
      JSON.stringify({
        columns: [
          { workflow: 'spec', type: 'interactive' },
          { workflow: 'build', type: 'auto' },
        ],
        counts: { ongoing: 1, need_you: 1, cancelled: 0, oldest_wait_at: new Date().toISOString() },
        items: [
          {
            attention: 'your_turn',
            id: '0193a000-0000-7000-8000-000000000001',
            line: 'ux · your turn · 14 turns',
            name: 'Initiative steps',
            position: 1,
            progress: '1 of 3 steps',
            project_id: '0193a000-0000-7000-8000-000000000002',
            project_name: 'Orchestrator',
            reason: '',
            repo_tag: ['ai-orchestrator'],
            repository_id: '0193a000-0000-7000-8000-000000000003',
            slug: 'initiative-steps',
            status: 'waiting for her',
            step: 'ux',
            updated_at: new Date().toISOString(),
            workflow: 'spec',
            workflow_count: 2,
            workflows: [
              { workflow: 'spec', type: 'interactive', state: 'ongoing' },
              { workflow: 'build', type: 'auto', state: null },
            ],
          },
        ],
        next_cursor: null,
      }),
    );
    return;
  }
  const projectMatch = pathname.match(/^\/api\/v1\/projects\/([^/]+)$/);
  if (projectMatch && request.method === 'GET') {
    const project = projects[projectMatch[1]];
    if (!project) return notFound(response, 'no Project has that id');
    send(response, 200, JSON_TYPE, JSON.stringify(project));
    return;
  }
  if (projectMatch && request.method === 'PUT') {
    const project = updateProject(projectMatch[1], await readJsonBody(request));
    if (!project) return notFound(response, 'no Project has that id');
    send(response, 200, JSON_TYPE, JSON.stringify(project));
    return;
  }
  if (pathname === `/api/v1/runs/${STOPPED_BUILD_RUN}` && request.method === 'GET') {
    send(
      response,
      200,
      JSON_TYPE,
      JSON.stringify({
        id: STOPPED_BUILD_RUN,
        status: 'needs_you',
        spend_usd: '1.00',
        budget_usd: null,
        branch: 'feat/familio-dessin-v2',
        repository: 'familio-web',
        template: 'initiative-hub-epic',
        version: 1,
      }),
    );
    return;
  }
  const drawerMatch = pathname.match(
    /^\/api\/v1\/runs\/([^/]+)\/steps\/(\d+)\/attempts\/(\d+)\/drawer$/,
  );
  if (drawerMatch && request.method === 'GET') {
    const seq = Number(drawerMatch[2]);
    const frame = 'epics[0].stories[0]';
    const rows = ['sync', 'build', 'verify', 'commit', 'push'].map((label, i) => ({
      kind: label === 'build' ? 'agent' : 'shell',
      label,
      path: `${frame}.${label}`,
      phase: i < 1 ? 'BEFORE' : i === 1 ? 'AGENT' : 'AFTER',
      seq: 10 + i,
      token: 'DON',
      with_resolved: {},
    }));
    const row = rows.find((r) => r.seq === seq) ?? rows[4];
    const body = {
      attempts: [{ n: 1, status: 'done' }],
      files_read: { state: 'not_recorded', paths: [] },
      files_written: { state: 'refs', commit: null, files: [], refs: ['main aaa1111 → bbb2222'] },
      header: {
        cost_usd: null,
        ended_at: '2026-11-23T10:02:00Z',
        exit_code: 0,
        gate: 'deterministic',
        kind: row.kind,
        label: row.label,
        n: 1,
        path: row.path,
        seq: row.seq,
        started_at: '2026-11-23T10:00:00Z',
        status: 'done',
        token: 'DON',
      },
      log: { attempt_id: 'att-1', reason: null, removed_at: null, state: 'text' },
      run_order: { frame, rows },
    };
    send(response, 200, JSON_TYPE, JSON.stringify(body));
    return;
  }
  if (/^\/api\/v1\/runs\/[^/]+\/files$/.test(pathname) && request.method === 'GET') {
    const path = new URL(request.url, 'http://stub').searchParams.get('path');
    if (path) {
      send(
        response,
        200,
        JSON_TYPE,
        JSON.stringify({ path, content: '# Design\n', size: 9, mtime: 0 }),
      );
      return;
    }
  }
  const filesByEpicMatch = pathname.match(/^\/api\/v1\/runs\/([^/]+)\/files-by-epic$/);
  if (filesByEpicMatch && request.method === 'GET') {
    const body = {
      epics: [
        {
          index: 0,
          title: 'models',
          folder: 'specs/epic-1-models',
          files: ['specs/epic-1-models/SPEC.md', 'specs/epic-1-models/stories.yaml'],
          stories: [
            {
              id: '1',
              title: 'model list',
              started: true,
              story_file: 'specs/epic-1-models/stories/1-model-list.md',
              changed: ['src/models.py', 'tests/test_models.py'],
            },
          ],
        },
      ],
    };
    send(response, 200, JSON_TYPE, JSON.stringify(body));
    return;
  }
  const filesByEpicDiffMatch = pathname.match(/^\/api\/v1\/runs\/([^/]+)\/files-by-epic\/diff$/);
  if (filesByEpicDiffMatch && request.method === 'GET') {
    const path = new URL(request.url, 'http://stub').searchParams.get('path') ?? '';
    const diff = `--- a/${path}\n+++ b/${path}\n-old\n+new\n`;
    send(
      response,
      200,
      JSON_TYPE,
      JSON.stringify({ path, from_sha: 'aaa1111', to_sha: 'bbb2222', diff }),
    );
    return;
  }
  const exportMatch = pathname.match(/^\/api\/v1\/projects\/([^/]+)\/trajectories\.jsonl$/);
  if (exportMatch && request.method === 'GET') {
    const project = projects[exportMatch[1]];
    if (!project) return notFound(response, 'no Project has that id');
    const lines = Array.from({ length: project.trajectory_count ?? 0 }, (_unused, n) =>
      JSON.stringify(sampleTrajectoryLine(project, n)),
    );
    const today = new Date().toISOString().slice(0, 10);
    send(response, 200, 'application/x-ndjson', lines.map((line) => `${line}\n`).join(''), {
      'Content-Disposition': `attachment; filename="trajectories-${project.slug}-${today}.jsonl"`,
    });
    return;
  }
  const addRepositoryMatch = pathname.match(/^\/api\/v1\/projects\/([^/]+)\/repositories$/);
  if (addRepositoryMatch && request.method === 'POST') {
    const repository = addRepository(addRepositoryMatch[1], await readJsonBody(request));
    if (!repository) return notFound(response, 'no Project has that id');
    send(response, 201, JSON_TYPE, JSON.stringify(repository));
    return;
  }
  const repositoryMatch = pathname.match(/^\/api\/v1\/repositories\/([^/]+)$/);
  if (repositoryMatch && request.method === 'PUT') {
    const repository = updateRepository(repositoryMatch[1], await readJsonBody(request));
    if (!repository) return notFound(response, 'no Repository has that id');
    send(response, 200, JSON_TYPE, JSON.stringify(repository));
    return;
  }
  const cloneCheckMatch = pathname.match(/^\/api\/v1\/repositories\/([^/]+)\/clone-check$/);
  if (cloneCheckMatch && request.method === 'POST') {
    const repositoryId = cloneCheckMatch[1];
    if (repositoryId === RECHECK_REPOSITORY_ID) {
      const result = rerunCloneCheck(repositoryId);
      if (!result) return notFound(response, 'no Repository has that id');
      send(response, 200, JSON_TYPE, JSON.stringify(result));
      return;
    }
    // any other id `projects.spec.ts` (2.4) already fixed at startup keeps 404ing, exactly
    // as before 2.5; only a Repository this story's own routes created gets a real check
    const repository = repositoriesById.get(repositoryId);
    if (!repository || STATIC_REPOSITORY_IDS.has(repositoryId)) {
      return notFound(response, 'no Repository has that id');
    }
    send(response, 200, JSON_TYPE, JSON.stringify(simulateCloneCheck(repository)));
    return;
  }
  const initMatch = pathname.match(/^\/api\/v1\/repositories\/([^/]+)\/init$/);
  if (initMatch && request.method === 'POST') {
    const result = initRepository(initMatch[1]);
    if (result.status === 404) return notFound(response, result.title);
    if (result.status === 409) {
      send(
        response,
        409,
        PROBLEM,
        JSON.stringify({
          type: 'about:blank',
          title: result.title,
          status: 409,
          detail: result.detail,
        }),
      );
      return;
    }
    send(response, result.status, JSON_TYPE, JSON.stringify(result.body));
    return;
  }
  if (initMatch && request.method === 'GET') {
    const repository = repositoriesById.get(initMatch[1]);
    if (!repository) return notFound(response, 'no Repository has that id');
    send(response, 200, JSON_TYPE, JSON.stringify(repository));
    return;
  }
  if (pathname === '/api/v1/templates' && request.method === 'GET') {
    // forced empty unconditionally (3.5's Design Notes): the frozen `shell.spec.ts` asserts
    // `NO TEMPLATES` at bare `/templates` against this same, `fullyParallel` stub
    send(response, 200, JSON_TYPE, JSON.stringify({ items: [], next_cursor: null }));
    return;
  }
  const templateVersionsMatch = pathname.match(/^\/api\/v1\/templates\/([^/]+)\/versions$/);
  if (templateVersionsMatch && request.method === 'GET') {
    const template = templates[templateVersionsMatch[1]];
    if (!template) return notFound(response, 'no Template has that name');
    const versionNumbers = Object.keys(template.versions)
      .map(Number)
      .sort((a, b) => a - b);
    send(response, 200, JSON_TYPE, JSON.stringify({ items: versionNumbers, next_cursor: null }));
    return;
  }
  if (templateVersionsMatch && request.method === 'POST') {
    const body = await readJsonBody(request);
    const result = saveTemplateVersion(templateVersionsMatch[1], body.yaml ?? '');
    send(
      response,
      result.status,
      result.status >= 400 ? PROBLEM : JSON_TYPE,
      JSON.stringify(result.body),
    );
    return;
  }
  const templateValidateMatch = pathname.match(/^\/api\/v1\/templates\/([^/]+)\/validate$/);
  if (templateValidateMatch && request.method === 'POST') {
    const body = await readJsonBody(request);
    send(response, 200, JSON_TYPE, JSON.stringify(validateYamlText(body.yaml ?? '')));
    return;
  }
  const templateVersionMatch = pathname.match(/^\/api\/v1\/templates\/([^/]+)\/(\d+)$/);
  if (templateVersionMatch && request.method === 'GET') {
    const template = templates[templateVersionMatch[1]];
    const version = template?.versions[Number(templateVersionMatch[2])];
    if (!version) {
      return notFound(response, 'no Template has that name, or no version has that number');
    }
    send(response, 200, JSON_TYPE, JSON.stringify(version));
    return;
  }
  const versionGraphMatch = pathname.match(/^\/api\/v1\/templates\/([^/]+)\/(\d+)\/graph$/);
  if (versionGraphMatch && request.method === 'GET') {
    const template = templates[versionGraphMatch[1]];
    const version = template?.versions[Number(versionGraphMatch[2])];
    if (!version) {
      return notFound(response, 'no Template has that name, or no version has that number');
    }
    send(response, 200, JSON_TYPE, JSON.stringify(graphFromYaml(version.yaml)));
    return;
  }
  const textGraphMatch = pathname.match(/^\/api\/v1\/templates\/([^/]+)\/graph$/);
  if (textGraphMatch && request.method === 'POST') {
    const body = await readJsonBody(request);
    const yamlText = body.yaml ?? '';
    const { errors } = validateYamlText(yamlText);
    if (errors.length > 0) {
      send(
        response,
        422,
        PROBLEM,
        JSON.stringify({
          type: 'about:blank',
          title: 'invalid template',
          status: 422,
          detail: `line ${errors[0].line}: ${errors[0].reason}`,
          errors,
        }),
      );
      return;
    }
    send(response, 200, JSON_TYPE, JSON.stringify(graphFromYaml(yamlText)));
    return;
  }
  send(response, 404, PROBLEM, JSON.stringify({ title: 'not found', status: 404 }));
}).listen(PORT, '127.0.0.1', () => {
  process.stdout.write(`stub backend listening on ${PORT}\n`);
});
