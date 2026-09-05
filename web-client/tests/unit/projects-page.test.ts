/**
 * `src/pages/projects/index.astro` itself, rendered end to end at the unit layer —
 * `astro/container` pattern from `components.test.ts`, `vi.stubGlobal('fetch', ...)` pattern
 * from `proxy.test.ts`. `check-test-pairs.mjs` exempts `src/pages/**` (its gate is
 * `make e2e-ui`), but the page's own list-population and error-handling branches are not
 * otherwise exercised anywhere: the e2e stub's `GET /api/v1/projects` always answers empty
 * (so the frozen `shell.spec.ts` keeps passing), and `projects-components.test.ts` renders
 * `ProjectListRow` directly with hand-picked props, never through `index.astro`'s own mapping
 * or its `selected`/`failedCount` derivation. This file drives that code path directly.
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProjectsIndexPage from '../../src/pages/projects/index.astro';

const REPOSITORY_DEFAULTS = {
  project_id: 'project-id-not-set',
  url: 'https://github.com/example/repo.git',
  default_branch: 'main',
  install_command: 'pnpm install',
  quality_gate_command: 'pnpm test',
  unit_test_command: 'pnpm test',
  test_globs: ['tests/**/*.test.ts'],
  package_manager: 'pnpm',
  clone_check_lines: [],
  clone_check_hint: '',
  verify_skipped: false,
  created_at: '2026-01-05T09:00:00Z',
  updated_at: '2026-01-06T10:00:00Z',
};

function okRepository(id: string, slug: string, projectId: string) {
  return {
    ...REPOSITORY_DEFAULTS,
    id,
    slug,
    project_id: projectId,
    clone_check: { status: 'ok', at: '2026-09-04T12:00:00Z', output: 'ok', bmad_version: '6.11.0' },
  };
}

function failedRepository(id: string, slug: string, projectId: string) {
  return {
    ...REPOSITORY_DEFAULTS,
    id,
    slug,
    project_id: projectId,
    clone_check: {
      status: 'failed',
      at: '2026-09-04T12:00:00Z',
      output: 'failed',
      bmad_version: null,
    },
  };
}

const PROJECT_DEFAULTS = {
  context_text: '',
  context_paths: [],
  env_vars: [],
  log_prompt_content: false,
  created_at: '2026-01-05T09:00:00Z',
  updated_at: '2026-01-06T10:00:00Z',
};

const FIRST = {
  ...PROJECT_DEFAULTS,
  id: '11111111-0000-4000-8000-000000000001',
  slug: 'first-project',
  name: 'First Project',
  repositories: [okRepository('r1', 'first-repo', '11111111-0000-4000-8000-000000000001')],
};

const SECOND = {
  ...PROJECT_DEFAULTS,
  id: '22222222-0000-4000-8000-000000000002',
  slug: 'second-project',
  name: 'Second Project',
  repositories: [
    failedRepository('r2', 'second-repo-a', '22222222-0000-4000-8000-000000000002'),
    okRepository('r3', 'second-repo-b', '22222222-0000-4000-8000-000000000002'),
  ],
};

let container: AstroContainer;

function stubProjectsList(response: Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((request: Request) => {
      const url = new URL(request.url);
      if (url.pathname === '/api/v1/projects') return Promise.resolve(response.clone());
      // the detail fetch a selected `?id=` also triggers: answered generically so the
      // list-focused assertions below never depend on it succeeding or failing
      return Promise.resolve(new Response(JSON.stringify(SECOND), { status: 200 }));
    }),
  );
}

async function render(url: string): Promise<string> {
  container = await AstroContainer.create();
  return container.renderToString(ProjectsIndexPage, {
    request: new Request(url),
  });
}

/** The one `<a>` a `ProjectListRow` with this slug renders, so a row's own text can be
 * checked in isolation from its siblings. */
function rowHtml(html: string, slug: string): string {
  const match = html.match(new RegExp(`<a[^>]*data-testid="projects-row-${slug}"[\\s\\S]*?</a>`));
  if (!match) throw new Error(`no row for slug "${slug}" in:\n${html}`);
  return match[0];
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the populated list (2.4 finding: list mapping was otherwise untested)', () => {
  it('marks the selected row, and only the selected row, from a real GET /api/v1/projects', async () => {
    stubProjectsList(
      new Response(JSON.stringify({ items: [FIRST, SECOND], next_cursor: null }), {
        status: 200,
      }),
    );

    const html = await render(`http://web-client.test/projects?id=${SECOND.id}`);

    expect(html).toMatch(/data-testid="projects-row-second-project"[^>]*data-selected="true"/);
    expect(html).toMatch(/data-testid="projects-row-first-project"[^>]*data-selected="false"/);
  });

  it('counts the failed Repositories per row, only where non-zero', async () => {
    stubProjectsList(
      new Response(JSON.stringify({ items: [FIRST, SECOND], next_cursor: null }), {
        status: 200,
      }),
    );

    const html = await render('http://web-client.test/projects');

    expect(rowHtml(html, 'first-project')).not.toContain('failed');
    expect(rowHtml(html, 'second-project')).toContain('1 failed');
  });

  it('reads "1 project", not "1 projects"', async () => {
    stubProjectsList(
      new Response(JSON.stringify({ items: [FIRST], next_cursor: null }), { status: 200 }),
    );

    const html = await render('http://web-client.test/projects');

    expect(html).toContain('1 project');
    expect(html).not.toContain('1 projects');
  });
});

describe('a list that could not be read (2.4 finding: error was coerced into "no Projects")', () => {
  it('renders a distinct unavailable state on a resolved error, not NO PROJECTS', async () => {
    stubProjectsList(
      new Response(JSON.stringify({ type: 'about:blank', title: 'error', status: 500 }), {
        status: 500,
      }),
    );

    const html = await render('http://web-client.test/projects');

    expect(html).toContain('data-testid="projects-list-error"');
    expect(html).not.toContain('data-testid="projects-empty"');
    expect(html).not.toContain('NO PROJECTS');
  });

  it('renders a distinct unavailable state on a rejected fetch, not NO PROJECTS', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new Error('network is down'))),
    );

    const html = await render('http://web-client.test/projects');

    expect(html).toContain('data-testid="projects-list-error"');
    expect(html).not.toContain('data-testid="projects-empty"');
    expect(html).not.toContain('NO PROJECTS');
  });

  it('still renders the genuine empty state distinctly, when the list truly is empty', async () => {
    stubProjectsList(
      new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200 }),
    );

    const html = await render('http://web-client.test/projects');

    expect(html).toContain('data-testid="projects-empty"');
    expect(html).toContain('NO PROJECTS');
    expect(html).not.toContain('data-testid="projects-list-error"');
  });
});
