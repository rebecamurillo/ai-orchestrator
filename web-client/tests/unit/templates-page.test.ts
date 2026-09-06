/**
 * `src/pages/templates/index.astro` itself, rendered end to end at the unit layer —
 * `astro/container` + `vi.stubGlobal('fetch', ...)` pattern from `tests/unit/projects-page.
 * test.ts` (2.4's own finding, applied here for the same reason). `check-test-pairs.mjs`
 * exempts `src/pages/**` (its gate is `make e2e-ui`), but the shared e2e stub forces
 * `GET /api/v1/templates` unconditionally empty (the story's Design Notes, matching frozen
 * `shell.spec.ts`), so this page's redirect-on-non-empty-list branch and its
 * `TEMPLATES UNAVAILABLE` branch were otherwise exercised by nothing at all (Review Triage
 * Log, story 3.5, finding 6). This file drives both directly.
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { afterEach, describe, expect, it, vi } from 'vitest';

import TemplatesIndexPage from '../../src/pages/templates/index.astro';

function stubTemplatesList(response: Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((request: Request) => {
      const url = new URL(request.url);
      if (url.pathname === '/api/v1/templates') return Promise.resolve(response.clone());
      return Promise.resolve(new Response('not found', { status: 404 }));
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('a non-empty list (Review Triage Log, story 3.5, finding 6)', () => {
  it('redirects to the latest version of the first Template by name', async () => {
    stubTemplatesList(
      new Response(
        JSON.stringify({
          items: [
            { name: 'story', description: null, latest_version: 3, versions: [1, 2, 3] },
            { name: 'epic', description: null, latest_version: 2, versions: [1, 2] },
          ],
          next_cursor: null,
        }),
        { status: 200 },
      ),
    );

    const container = await AstroContainer.create();
    const response = await container.renderToResponse(TemplatesIndexPage, {
      request: new Request('http://web-client.test/templates'),
    });

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe('/templates/epic/2');
  });
});

describe('a list that could not be read (Review Triage Log, story 3.5, finding 6)', () => {
  it('renders a distinct unavailable state on a resolved error, not NO TEMPLATES', async () => {
    stubTemplatesList(
      new Response(JSON.stringify({ type: 'about:blank', title: 'error', status: 500 }), {
        status: 500,
      }),
    );

    const container = await AstroContainer.create();
    const html = await container.renderToString(TemplatesIndexPage, {
      request: new Request('http://web-client.test/templates'),
    });

    expect(html).toContain('data-testid="templates-list-error"');
    expect(html).toContain('TEMPLATES UNAVAILABLE');
    expect(html).not.toContain('data-testid="templates-empty"');
  });

  it('renders a distinct unavailable state on a rejected fetch, not NO TEMPLATES', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new Error('network is down'))),
    );

    const container = await AstroContainer.create();
    const html = await container.renderToString(TemplatesIndexPage, {
      request: new Request('http://web-client.test/templates'),
    });

    expect(html).toContain('data-testid="templates-list-error"');
    expect(html).not.toContain('data-testid="templates-empty"');
  });
});

describe('a genuinely empty list', () => {
  it('renders NO TEMPLATES, not TEMPLATES UNAVAILABLE', async () => {
    stubTemplatesList(
      new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200 }),
    );

    const container = await AstroContainer.create();
    const html = await container.renderToString(TemplatesIndexPage, {
      request: new Request('http://web-client.test/templates'),
    });

    expect(html).toContain('data-testid="templates-empty"');
    expect(html).toContain('NO TEMPLATES');
    expect(html).not.toContain('data-testid="templates-list-error"');
  });
});
