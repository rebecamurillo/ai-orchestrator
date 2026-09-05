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
 */
import { createServer } from 'node:http';

import { PROJECTS_BY_ID, RECHECK_REPOSITORY_ID } from './projects-fixtures.mjs';

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
  if (pathname === '/api/v1/projects') {
    send(response, 200, JSON_TYPE, JSON.stringify({ items: [], next_cursor: null }));
    return;
  }
  const projectMatch = pathname.match(/^\/api\/v1\/projects\/([^/]+)$/);
  if (projectMatch) {
    const project = projects[projectMatch[1]];
    if (!project) return notFound(response, 'no Project has that id');
    send(response, 200, JSON_TYPE, JSON.stringify(project));
    return;
  }
  const cloneCheckMatch = pathname.match(/^\/api\/v1\/repositories\/([^/]+)\/clone-check$/);
  if (cloneCheckMatch && request.method === 'POST') {
    const result = rerunCloneCheck(cloneCheckMatch[1]);
    if (!result) return notFound(response, 'no Repository has that id');
    send(response, 200, JSON_TYPE, JSON.stringify(result));
    return;
  }
  send(response, 404, PROBLEM, JSON.stringify({ title: 'not found', status: 404 }));
}).listen(PORT, '127.0.0.1', () => {
  process.stdout.write(`stub backend listening on ${PORT}\n`);
});
