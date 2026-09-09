/**
 * The Run the UJ-3 browser journey drives (6.8, SPEC CAP-8, UJ-3).
 *
 * `uj3.spec.ts` is the only spec in this suite whose subject is not "what does the screen do
 * with this response" but "what does the Operator do with a real Run", so it is the only one
 * that needs a real Run to exist. This module makes one, the same way
 * `backend-api/tests/e2e/helpers/gates_fixture.py` does and for the same reasons: a bare
 * origin holding `fixtures/gates-repo/` with a `_bmad/` manifest stating the instance's own
 * `BMAD_VERSION` (AD-16, never committed — it would go stale at the next pin bump), created
 * either on this host or inside the `backend-api` container, whichever can see the work
 * directory the backend clones into.
 *
 * It runs only under `E2E_BACKEND=real`, against a stack in test mode (`ORCH_TEST_MODE=1`)
 * so the scripted `fake` harness is registered. When the caller has exported
 * `COMPOSE_PROJECT_NAME` / `COMPOSE_FILE` / `COMPOSE_ENV_FILE` — which is how the disposable
 * `aio-e2e` stack is addressed — those are honoured, so the journey talks to the same stack
 * the API scenarios do rather than to whatever `docker compose` would pick by default.
 *
 * TypeScript rather than the `.mjs` `projects-fixtures.mjs` is: that file is shared with the
 * `.mjs` stub server, which runs outside Astro's pipeline and cannot resolve a `.ts` module.
 * Nothing but a spec imports this one, and a spec is compiled by Playwright.
 *
 * Nothing here asserts: a failure throws with what it tried, and the spec reports it.
 */
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(HERE, '..', '..', '..');

/** The fixture's source, per topology — the checkout here, `/app/fixtures` in the image. */
const SOURCE_HERE = join(REPO_ROOT, 'fixtures', 'gates-repo');
const SOURCE_IN_CONTAINER = '/app/fixtures/gates-repo';

/** Where this suite's bare repositories live, under the work directory both routes share. */
const FIXTURE_DIRECTORY = 'e2e-fixtures';

const SPEC_FOLDER = 'specs/gates';
/** The spec-folder-scoped gate, so story 3's own `verify` fails (see the fixture README). */
const QUALITY_GATE = 'sh check-spec.sh';

const EPIC_TEMPLATE = join(REPO_ROOT, 'templates', 'epic.yaml');
const NAME_LINE = 'name: epic\n';

const POLL_MS = 1000;
const DEFAULT_TIMEOUT_MS = 300_000;

/** `backend-api/tests/e2e/helpers/gates_fixture.py::MAKE_GATES_ORIGIN`, verbatim. */
const MAKE_GATES_ORIGIN = `
set -e
dir="$1"; name="$2"; source="$3"; version="$4"
mkdir -p "$dir"
rm -rf "$dir/$name.git" "$dir/$name.seed"
git init --quiet --bare --initial-branch=main "$dir/$name.git"
cp -R "$source" "$dir/$name.seed"
cd "$dir/$name.seed"
mkdir -p _bmad/_config
printf 'installation:\\n  version: %s\\n  installDate: 2026-09-09\\nmodules: []\\n' \\
  "$version" > _bmad/_config/manifest.yaml
git init --quiet --initial-branch=main
git config user.email e2e@example.invalid
git config user.name e2e
git add --all
git commit --quiet --message "gates fixture: seed"
git push --quiet "$dir/$name.git" main:main
git --git-dir="$dir/$name.git" symbolic-ref HEAD refs/heads/main
`;

/** The two settings this module needs out of the backend's own environment. */
const READ_SETTINGS = `
set -e
printf '%s\\n%s\\n' "$BMAD_VERSION" "$WORK_DIR"
`;

export interface StackSettings {
  bmadVersion: string;
  workDir: string;
}

export interface ParkedRun {
  runId: string;
  projectId: string;
}

interface RunDetail {
  run: { status: string; id: string };
  alert: { park_kind: string | null; reason: string | null } | null;
  steps: { path: string; status: string }[];
}

function composeArgs(): string[] {
  const args = ['compose'];
  if (process.env.COMPOSE_PROJECT_NAME) args.push('-p', process.env.COMPOSE_PROJECT_NAME);
  for (const file of (process.env.COMPOSE_FILE ?? '').split(':').filter(Boolean)) {
    args.push('-f', file);
  }
  if (process.env.COMPOSE_ENV_FILE) args.push('--env-file', process.env.COMPOSE_ENV_FILE);
  return args;
}

/** Run `script` here, else inside the backend container; throw naming both refusals. */
function either(script: string, hereArgs: string[], insideArgs: string[], what: string): string {
  const refusals: string[] = [];
  const routes: [string, string[], string][] = [
    ['sh', ['-c', script, 'sh', ...hereArgs], 'on this host'],
    [
      'docker',
      [...composeArgs(), 'exec', '-T', 'backend-api', 'sh', '-c', script, 'sh', ...insideArgs],
      'in the backend-api container',
    ],
  ];
  for (const [command, args, where] of routes) {
    try {
      return execFileSync(command, args, { cwd: REPO_ROOT, encoding: 'utf8', stdio: 'pipe' });
    } catch (error) {
      refusals.push(`${where}: ${said(error)}`);
    }
  }
  throw new Error(`no route to ${what}: ${refusals.join(' | ')}`);
}

function said(error: unknown): string {
  const failure = error as { stderr?: string; stdout?: string };
  return (failure.stderr || failure.stdout || String(error)).trim();
}

/** `BMAD_VERSION` and `WORK_DIR`, from this shell if it has them, else from the backend. */
export function backendSettings(): StackSettings {
  if (process.env.BMAD_VERSION && process.env.WORK_DIR) {
    return { bmadVersion: process.env.BMAD_VERSION, workDir: process.env.WORK_DIR };
  }
  const read = either(READ_SETTINGS, [], [], 'read BMAD_VERSION and WORK_DIR');
  const [bmadVersion = '', workDir = ''] = read.split('\n').map((line) => line.trim());
  if (!bmadVersion || !workDir) {
    throw new Error(`the stack reported BMAD_VERSION=${bmadVersion} WORK_DIR=${workDir}`);
  }
  return { bmadVersion, workDir };
}

/** A fresh bare origin holding the gates fixture on `main`; returns its `file://` URL. */
export function makeGatesOrigin({ bmadVersion, workDir }: StackSettings): string {
  const directory = `${workDir}/${FIXTURE_DIRECTORY}`;
  const name = `gates-ui-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  either(
    MAKE_GATES_ORIGIN,
    [directory, name, SOURCE_HERE, bmadVersion],
    [directory, name, SOURCE_IN_CONTAINER, bmadVersion],
    'create the gates fixture',
  );
  return `file://${directory}/${name}.git`;
}

/** `templates/epic.yaml` under a name of this suite's own — `epic@1` must stay unpinned. */
export function epicTemplateAs(name: string): string {
  const yaml = readFileSync(EPIC_TEMPLATE, 'utf8');
  if (!yaml.includes(NAME_LINE)) throw new Error(`${EPIC_TEMPLATE} no longer opens with a name`);
  return yaml.replace(NAME_LINE, `name: ${name}\n`);
}

/** One authenticated call against the backend, with the body parsed and errors named. */
async function call<T>(
  base: string,
  token: string,
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${method} ${path} answered ${response.status}: ${text}`);
  return (text ? JSON.parse(text) : null) as T;
}

/** Fail by name when the stack is not in test mode, rather than timing out later. */
async function requireTestMode(base: string, token: string): Promise<void> {
  const harnesses = await call<{ items: { name: string; enabled: boolean }[] }>(
    base,
    token,
    'GET',
    '/api/v1/harnesses',
  );
  if (!harnesses.items.find((item) => item.name === 'fake')?.enabled) {
    throw new Error(
      'the `fake` harness is not seeded: this journey needs a stack with ORCH_TEST_MODE=1',
    );
  }
}

/**
 * A Run on a fresh gates clone, walked until it parks `blocked` on story 1.
 *
 * Returns the Run and its Project: the Board is opened filtered to that Project, the way
 * `index.astro` resolves a `?project=` deep link, and the card is found by the Run's own id.
 */
export async function startParkedRun(
  base: string,
  token: string,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<ParkedRun> {
  await requireTestMode(base, token);
  const settings = backendSettings();

  const project = await call<{ id: string }>(base, token, 'POST', '/api/v1/projects', {
    name: `uj3 journey ${Date.now()}`,
  });
  const repository = await call<{ id: string }>(
    base,
    token,
    'POST',
    `/api/v1/projects/${project.id}/repositories`,
    { url: makeGatesOrigin(settings), default_branch: 'main', quality_gate_command: QUALITY_GATE },
  );
  const check = await call<{ status: string }>(
    base,
    token,
    'POST',
    `/api/v1/repositories/${repository.id}/clone-check`,
  );
  if (check.status !== 'ok') throw new Error(`clone check said ${JSON.stringify(check)}`);

  const templateName = `e2e-uj3-ui-${Date.now().toString(36)}`;
  await call(base, token, 'POST', `/api/v1/templates/${templateName}/versions`, {
    yaml: epicTemplateAs(templateName),
  });

  const started = await call<{ run: { id: string } }>(base, token, 'POST', '/api/v1/runs', {
    template_name: templateName,
    template_version: 1,
    project_id: project.id,
    repository_id: repository.id,
    base_branch: 'main',
    budget_usd: '5',
    harness: 'fake',
    inputs: { spec_folder: SPEC_FOLDER, branch: `epics/gates-ui-${Date.now().toString(36)}` },
  });
  const runId = started.run.id;

  await waitFor(
    base,
    token,
    runId,
    (detail) => detail.run.status === 'needs_you' && detail.alert?.park_kind === 'blocked',
    'the Run parking blocked on story 1',
    timeoutMs,
  );
  return { runId, projectId: project.id };
}

/** Poll `GET /runs/{id}/detail` until `done(detail)`, or throw naming the last state. */
export async function waitFor(
  base: string,
  token: string,
  runId: string,
  done: (detail: RunDetail) => boolean,
  what: string,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<RunDetail> {
  const deadline = Date.now() + timeoutMs;
  const read = () => call<RunDetail>(base, token, 'GET', `/api/v1/runs/${runId}/detail`);
  let detail = await read();
  while (Date.now() < deadline) {
    if (done(detail)) return detail;
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    detail = await read();
  }
  const rows = detail.steps.map((step) => `${step.path}=${step.status}`).join(' ');
  throw new Error(
    `${what} did not happen within ${timeoutMs / 1000}s — the Run is ${detail.run.status} ` +
      `at ${detail.alert?.park_kind ?? '-'}: ${detail.alert?.reason ?? '-'}; rows: ${rows}`,
  );
}

/**
 * `PUT /runs/{id}/files` — the Operator's inline repair, made through the API rather than
 * through the ARTIFACTS editor.
 *
 * The editor edits a file the tree lists, and the file this journey has to put back was
 * *deleted* by the scripted agent, so it is not in the tree to select. Creating it is what
 * the endpoint does and what the panel has no control for; the panel's own editing is
 * covered in a browser by `run-detail-artifacts.spec.ts`.
 */
export async function putFile(
  base: string,
  token: string,
  runId: string,
  path: string,
  content: string,
): Promise<{ path: string; mtime: number }> {
  return call(base, token, 'PUT', `/api/v1/runs/${runId}/files`, { path, content });
}

/** Cancel a Run so it holds neither a global slot nor its Repository's partition (AD-12). */
export async function cancelRun(base: string, token: string, runId: string): Promise<void> {
  await fetch(`${base}/api/v1/runs/${runId}/signals`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind: 'cancel', payload: { confirm: true } }),
  });
}
