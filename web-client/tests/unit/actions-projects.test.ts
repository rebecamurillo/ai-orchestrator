/**
 * The `save` Action behind `ProjectForm.tsx` (2.5), exercised without a browser — the same
 * `vi.stubGlobal('fetch', ...)` and `Symbol.for('astro.actionAPIContext')` pattern
 * `actions-repositories.test.ts` and `actions.test.ts` use, since `defineAction` refuses to
 * run a handler whose `this` is not marked as one.
 *
 * Responses are queued in call order: `save` makes several `fetch` calls per submission
 * (one per resource write, one per clone-check, one final read), and openapi-fetch calls
 * `fetch(request)` with a single `Request` rather than a url and an init bag.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { server } from '../../src/actions/index';
import { save, type SaveFailure } from '../../src/actions/projects';

const ACTION_CONTEXT = Symbol.for('astro.actionAPIContext');

interface Seen {
  method: string;
  path: string;
  body: unknown;
}

let seen: Seen[];

function stubUpstream(responses: Response[]): void {
  let index = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      const text = await request.clone().text();
      const body = text.length > 0 ? JSON.parse(text) : undefined;
      seen.push({ method: request.method, path: new URL(request.url).pathname, body });
      const response = responses[Math.min(index, responses.length - 1)]!;
      index += 1;
      return response;
    }),
  );
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  });
}

function context() {
  return { [ACTION_CONTEXT]: true };
}

function submit(form: FormData): Promise<unknown> {
  return save.orThrow.call(context(), form);
}

function baseForm(mode: 'create' | 'edit', projectId?: string): FormData {
  const form = new FormData();
  form.set('mode', mode);
  if (projectId) form.set('project_id', projectId);
  form.set('name', 'Mixed Signals');
  form.set('context_text', 'the context');
  form.set('context_paths', 'docs/architecture.md');
  return form;
}

function setEnvVar(form: FormData, index: number, row: Record<string, string>): void {
  for (const [field, value] of Object.entries(row)) {
    form.set(`env_vars[${index}].${field}`, value);
  }
}

function setRepository(form: FormData, index: number, row: Record<string, string>): void {
  for (const [field, value] of Object.entries(row)) {
    form.set(`repositories[${index}].${field}`, value);
  }
}

const REPO_A = {
  url: 'https://github.com/example/api.git',
  default_branch: 'main',
  package_manager: 'pnpm',
  test_globs: 'tests/**',
  install_command: 'pnpm install',
  quality_gate_command: 'pnpm lint && pnpm test',
  unit_test_command: 'pnpm test',
};

const REPO_B = {
  ...REPO_A,
  url: 'https://github.com/example/web.git',
};

function projectRead(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: 'project-1',
    slug: 'mixed-signals',
    name: 'Mixed Signals',
    context_text: 'the context',
    context_paths: ['docs/architecture.md'],
    env_vars: [],
    log_prompt_content: false,
    repositories: [],
    created_at: '2026-01-05T09:00:00Z',
    updated_at: '2026-01-05T09:00:00Z',
    ...overrides,
  };
}

function repositoryOut(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    id: 'repo-1',
    project_id: 'project-1',
    slug: 'repo',
    url: REPO_A.url,
    default_branch: REPO_A.default_branch,
    install_command: REPO_A.install_command,
    quality_gate_command: REPO_A.quality_gate_command,
    unit_test_command: REPO_A.unit_test_command,
    test_globs: ['tests/**'],
    package_manager: REPO_A.package_manager,
    clone_check: { status: 'pending', at: null, output: '', bmad_version: null },
    clone_check_lines: [],
    clone_check_hint: '',
    verify_skipped: false,
    created_at: '2026-01-05T09:00:00Z',
    updated_at: '2026-01-05T09:00:00Z',
    ...overrides,
  };
}

const CLONE_CHECK_RESULT = {
  status: 'ok',
  at: '2026-09-04T12:00:00Z',
  output: 'cloned ok',
  bmad_version: '6.11.0',
  lines: [],
  hint: '',
};

function problem(status: number, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { type: 'about:blank', title: 'problem', status, ...extra };
}

async function failure(promise: Promise<unknown>): Promise<SaveFailure> {
  await expect(promise).rejects.toThrow();
  try {
    await promise;
  } catch (error) {
    return JSON.parse((error as Error).message) as SaveFailure;
  }
  throw new Error('unreachable');
}

beforeEach(() => {
  seen = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe('the registry Astro builds `astro:actions` from', () => {
  it('exports the save Action under projects, beside login and repositories', () => {
    expect(server.projects.save).toBe(save);
  });
});

describe('create', () => {
  it('creates the project, each repository, an explicit clone-check per repository, then reads back', async () => {
    const form = baseForm('create');
    setEnvVar(form, 0, { name: 'NODE_ENV', value: 'production' });
    setRepository(form, 0, REPO_A);
    setRepository(form, 1, REPO_B);

    stubUpstream([
      json(201, projectRead()),
      json(201, repositoryOut({ id: 'repo-a', slug: 'api' })),
      json(201, repositoryOut({ id: 'repo-b', slug: 'web', url: REPO_B.url })),
      json(200, CLONE_CHECK_RESULT),
      json(200, CLONE_CHECK_RESULT),
      json(200, projectRead({ id: 'project-1', slug: 'mixed-signals' })),
    ]);

    await expect(submit(form)).resolves.toEqual({ id: 'project-1', slug: 'mixed-signals' });

    expect(seen.map((call) => `${call.method} ${call.path}`)).toEqual([
      'POST /api/v1/projects',
      'POST /api/v1/projects/project-1/repositories',
      'POST /api/v1/projects/project-1/repositories',
      'POST /api/v1/repositories/repo-a/clone-check',
      'POST /api/v1/repositories/repo-b/clone-check',
      'GET /api/v1/projects/project-1',
    ]);

    expect(seen[0]!.body).toMatchObject({
      name: 'Mixed Signals',
      context_paths: ['docs/architecture.md'],
      env_vars: [{ name: 'NODE_ENV', value: 'production' }],
    });
    expect(seen[1]!.body).toMatchObject({ url: REPO_A.url, default_branch: 'main' });
    expect(seen[2]!.body).toMatchObject({ url: REPO_B.url });
  });

  it('sends a checked log_prompt_content switch through to the project payload', async () => {
    const form = baseForm('create');
    form.set('log_prompt_content', 'on');

    stubUpstream([json(201, projectRead({ log_prompt_content: true }))]);

    await submit(form);

    expect(seen[0]!.body).toMatchObject({ log_prompt_content: true });
  });

  it('fails required-field checks before making any backend call, keeping every value', async () => {
    const form = baseForm('create');
    setRepository(form, 0, REPO_A);
    setRepository(form, 1, { ...REPO_B, default_branch: '' });

    const result = await failure(submit(form));

    expect(seen).toEqual([]);
    expect(result.errors).toEqual([{ path: 'repositories[1].default_branch', reason: 'required' }]);
    expect(result.draft.repositories[1]).toMatchObject({ url: REPO_B.url, defaultBranch: '' });
    expect(result.draft.repositories[0]).toMatchObject({ url: REPO_A.url });
  });

  it('refuses two rows sharing a url before making any backend call, as a conflict with no field path', async () => {
    const form = baseForm('create');
    setRepository(form, 0, REPO_A);
    setRepository(form, 1, REPO_A);

    const result = await failure(submit(form));

    expect(seen).toEqual([]);
    expect(result.errors).toBeUndefined();
    expect(result.detail).toContain('share the same url');
  });

  it('refuses a missing name before making any backend call', async () => {
    const form = baseForm('create');
    form.set('name', '');

    const result = await failure(submit(form));

    expect(seen).toEqual([]);
    expect(result.errors).toEqual([{ path: 'name', reason: 'required' }]);
  });

  it('surfaces a 422 on the project payload, remapped to the exact submitted field', async () => {
    const form = baseForm('create');
    setEnvVar(form, 0, { name: 'GITHUB_TOKEN', value: 'x' });

    stubUpstream([
      json(
        422,
        problem(422, {
          detail: 'body.env_vars.0.name: instance setting, not a project variable',
          errors: [
            { path: 'body.env_vars.0.name', reason: 'instance setting, not a project variable' },
          ],
        }),
      ),
    ]);

    const result = await failure(submit(form));

    expect(seen).toHaveLength(1);
    expect(result.errors).toEqual([
      { path: 'env_vars[0].name', reason: 'instance setting, not a project variable' },
    ]);
    expect(result.draft.envVars[0]).toMatchObject({ name: 'GITHUB_TOKEN', value: 'x' });
  });

  it('surfaces a 422 on one repository row, remapped to that row', async () => {
    const form = baseForm('create');
    setRepository(form, 0, REPO_A);
    setRepository(form, 1, { ...REPO_B, test_globs: '../x' });

    stubUpstream([
      json(201, projectRead()),
      json(201, repositoryOut({ id: 'repo-a', slug: 'api' })),
      json(
        422,
        problem(422, {
          detail: 'body.test_globs.0: no leading `/`, no `..` segment',
          errors: [{ path: 'body.test_globs.0', reason: 'no leading `/`, no `..` segment' }],
        }),
      ),
    ]);

    const result = await failure(submit(form));

    expect(seen.map((call) => `${call.method} ${call.path}`)).toEqual([
      'POST /api/v1/projects',
      'POST /api/v1/projects/project-1/repositories',
      'POST /api/v1/projects/project-1/repositories',
    ]);
    expect(result.errors).toEqual([
      { path: 'repositories[1].test_globs[0]', reason: 'no leading `/`, no `..` segment' },
    ]);
  });

  it('surfaces a 409 with no field path, printed as detail', async () => {
    const form = baseForm('create');

    stubUpstream([
      json(409, problem(409, { title: 'conflict', detail: 'a Project already has that name' })),
    ]);

    const result = await failure(submit(form));

    expect(result.errors).toBeUndefined();
    expect(result.detail).toBe('a Project already has that name');
  });
});

describe('update', () => {
  it('PUTs existing rows, POSTs new rows, then the same clone-check-then-read tail', async () => {
    const form = baseForm('edit', 'project-1');
    setEnvVar(form, 0, { name: 'NODE_ENV', masked: '****ion' });
    setRepository(form, 0, { ...REPO_A, id: 'repo-a' });
    setRepository(form, 1, REPO_B);

    stubUpstream([
      json(200, projectRead()),
      json(200, repositoryOut({ id: 'repo-a', slug: 'api' })),
      json(201, repositoryOut({ id: 'repo-b', slug: 'web', url: REPO_B.url })),
      json(200, CLONE_CHECK_RESULT),
      json(200, CLONE_CHECK_RESULT),
      json(200, projectRead()),
    ]);

    await expect(submit(form)).resolves.toEqual({ id: 'project-1', slug: 'mixed-signals' });

    expect(seen.map((call) => `${call.method} ${call.path}`)).toEqual([
      'PUT /api/v1/projects/project-1',
      'PUT /api/v1/repositories/repo-a',
      'POST /api/v1/projects/project-1/repositories',
      'POST /api/v1/repositories/repo-a/clone-check',
      'POST /api/v1/repositories/repo-b/clone-check',
      'GET /api/v1/projects/project-1',
    ]);
  });

  it('sends a kept env var with no value key at all, so the backend keeps the stored ciphertext', async () => {
    const form = baseForm('edit', 'project-1');
    setEnvVar(form, 0, { name: 'NODE_ENV', masked: '****ion' });

    stubUpstream([json(200, projectRead()), json(200, projectRead())]);

    await submit(form);

    const body = seen[0]!.body as { env_vars: Array<{ name: string; value?: string }> };
    expect(body.env_vars).toEqual([{ name: 'NODE_ENV' }]);
    expect(body.env_vars[0]).not.toHaveProperty('value');
  });

  it('sends a replaced env var with its new value', async () => {
    const form = baseForm('edit', 'project-1');
    setEnvVar(form, 0, { name: 'NODE_ENV', value: 'staging' });

    stubUpstream([json(200, projectRead()), json(200, projectRead())]);

    await submit(form);

    const body = seen[0]!.body as { env_vars: Array<{ name: string; value?: string }> };
    expect(body.env_vars).toEqual([{ name: 'NODE_ENV', value: 'staging' }]);
  });

  it('refuses a duplicate name as a 409 with no field path, before touching any repository', async () => {
    const form = baseForm('edit', 'project-1');
    setRepository(form, 0, REPO_A);

    stubUpstream([
      json(409, problem(409, { title: 'conflict', detail: 'a Project already has that name' })),
    ]);

    const result = await failure(submit(form));

    expect(seen).toHaveLength(1);
    expect(result.errors).toBeUndefined();
    expect(result.detail).toBe('a Project already has that name');
  });
});
