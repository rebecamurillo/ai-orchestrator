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
 */
import { createHash, randomUUID } from 'node:crypto';
import { createServer } from 'node:http';

import { PROJECTS_BY_ID, RECHECK_REPOSITORY_ID } from './projects-fixtures.mjs';
import { TEMPLATES } from './templates-fixtures.mjs';

const PORT = Number(process.env.STUB_BACKEND_PORT ?? 8788);
const TOKEN = process.env.ORCHESTRATOR_TOKEN ?? '';

const PROBLEM = 'application/problem+json';
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
  if (pathname === '/api/v1/projects' && request.method === 'GET') {
    send(response, 200, JSON_TYPE, JSON.stringify({ items: [], next_cursor: null }));
    return;
  }
  if (pathname === '/api/v1/projects' && request.method === 'POST') {
    const project = createProject(await readJsonBody(request));
    send(response, 201, JSON_TYPE, JSON.stringify(project));
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
  send(response, 404, PROBLEM, JSON.stringify({ title: 'not found', status: 404 }));
}).listen(PORT, '127.0.0.1', () => {
  process.stdout.write(`stub backend listening on ${PORT}\n`);
});
