/**
 * Where a Project row in the list actually goes.
 *
 * Clicking a row used to set `?id=`, which selected a detail pane rendered *after* the whole
 * list — on a populated list that pane opens hundreds of rows below the fold, so the click
 * read as "the page reloaded and nothing happened". The row now opens the edit page directly.
 *
 * Nothing in the suite could catch that: `tests/e2e/projects.spec.ts` navigates to `?id=`
 * by URL and never clicks a row, because the e2e stub's `GET /api/v1/projects` answers an
 * empty list unconditionally, and `tests/unit/projects-components.test.ts` renders
 * `ProjectListRow` with `href` handed in as a prop, so it asserts the component honours a
 * link target rather than which target the page chooses. The choice is `index.astro`'s, and
 * this file is what holds it: the page is rendered with a real populated list, exactly as
 * `projects-page.test.ts` does, and the rendered `href` is read back off the row.
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProjectsIndexPage from '../../src/pages/projects/index.astro';

const PROJECT_DEFAULTS = {
  context_text: '',
  context_paths: [],
  env_vars: [],
  log_prompt_content: false,
  repositories: [],
  created_at: '2026-01-05T09:00:00Z',
  updated_at: '2026-01-06T10:00:00Z',
};

const FIRST = {
  ...PROJECT_DEFAULTS,
  id: '11111111-0000-4000-8000-000000000001',
  slug: 'first-project',
  name: 'First Project',
};

const SECOND = {
  ...PROJECT_DEFAULTS,
  id: '22222222-0000-4000-8000-000000000002',
  slug: 'second-project',
  name: 'Second Project',
};

function stubBackend(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((request: Request) => {
      const url = new URL(request.url);
      if (url.pathname === '/api/v1/projects') {
        return Promise.resolve(
          new Response(JSON.stringify({ items: [FIRST, SECOND], next_cursor: null }), {
            status: 200,
          }),
        );
      }
      return Promise.resolve(new Response(JSON.stringify(SECOND), { status: 200 }));
    }),
  );
}

async function render(url: string): Promise<string> {
  const container = await AstroContainer.create();
  return container.renderToString(ProjectsIndexPage, { request: new Request(url) });
}

/** The `href` of the one row carrying this slug. */
function rowHref(html: string, slug: string): string {
  const match = html.match(
    new RegExp(`<a[^>]*data-testid="projects-row-${slug}"[^>]*href="([^"]*)"`),
  );
  if (!match) throw new Error(`no row for slug "${slug}" in:\n${html}`);
  return match[1];
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('a Project row opens the edit page', () => {
  it('links each row at that Project’s own edit route', async () => {
    stubBackend();

    const html = await render('http://web-client.test/projects');

    expect(rowHref(html, 'first-project')).toBe(`/projects/${FIRST.id}/edit`);
    expect(rowHref(html, 'second-project')).toBe(`/projects/${SECOND.id}/edit`);
  });

  it('leaves no row pointing at the select-then-edit form', async () => {
    stubBackend();

    const html = await render('http://web-client.test/projects');

    for (const slug of ['first-project', 'second-project']) {
      expect(rowHref(html, slug)).not.toContain('?id=');
    }
  });

  it('keeps the row target independent of which Project is selected', async () => {
    stubBackend();

    const html = await render(`http://web-client.test/projects?id=${SECOND.id}`);

    expect(rowHref(html, 'second-project')).toBe(`/projects/${SECOND.id}/edit`);
    expect(rowHref(html, 'first-project')).toBe(`/projects/${FIRST.id}/edit`);
  });
});
