/** Story 10.5: PackageSection.astro and its mount on the projects page (AC1–AC5, AC9). */
import { getContainerRenderer } from '@astrojs/react';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { loadRenderers } from 'astro:container';
import { afterEach, describe, expect, it, vi } from 'vitest';

import PackageSection from '../../src/components/projects/PackageSection.astro';
import ProjectsIndexPage from '../../src/pages/projects/index.astro';

const ID = '11111111-0000-4000-8000-000000000001';
const HUB = 'hub-id';
const repos = [
  { id: 'other-id', slug: 'other' },
  { id: HUB, slug: 'hub' },
];
const step = (id: string, persona: string) => ({
  id,
  persona,
  kind: 'conversation',
  file: null,
  skill: null,
  writes: [],
});
const entry = (workflow: string, type: string, shown_as: string, steps: unknown[] = []) => ({
  workflow,
  type,
  shown_as,
  steps,
  template: workflow,
  version: null,
});
const pkg = {
  name: 'rebecamurillo-initiatives',
  installed_at: '2026-11-20T10:00:00Z',
  repository_id: HUB,
  path: 'package',
  ref: 'main',
  sequence: [
    entry('spec', 'interactive', 'workflow', [step('brief', 'analyst'), step('check', 'reviewer')]),
    entry('merge', 'auto', 'step'),
    entry('build', 'auto', 'workflow'),
  ],
  status_map: { final: 'done', blocked: 'waiting for her' },
};
const none = { install: null, remove: null };

const container = () =>
  loadRenderers([getContainerRenderer()]).then((renderers) => AstroContainer.create({ renderers }));
async function section(props: Record<string, unknown>): Promise<string> {
  return (await container()).renderToString(PackageSection, {
    props: { projectId: ID, repositories: repos, refusal: none, ...props },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe('PackageSection', () => {
  it('AC1/AC2/AC4: the kv block, hint and both forms for an installed package', async () => {
    const html = await section({ pkg });
    expect(html).toContain('rebecamurillo-initiatives');
    expect(html).toContain('2026-11-20');
    expect(html).toContain('spec interactive ▸ build auto');
    expect(html).toContain('brief · analyst, check · reviewer, merge · automatic');
    expect(html).not.toContain('steps build');
    expect(html).toContain('final → DON');
    expect(html).toContain('blocked → BLK');
    expect(html).toContain(
      'Initiatives already started keep their sequence; agent and skill edits apply from their next step.',
    );
    expect(html).toContain('Replace package');
    expect(html).not.toContain('Install package');
    expect(html).toMatch(/<option value="hub-id"[^>]*selected/);
    expect(html).toMatch(/name="path"[^>]*value="package"/);
    expect(html).toMatch(/name="ref"[^>]*value="main"/);
    expect(html).toMatch(
      /data-variant="destructive"[^>]*data-testid="projects-package-remove"|data-testid="projects-package-remove"[^>]*data-variant="destructive"/,
    );
    expect(html).toContain('_action=packages.install');
    expect(html).toContain('_action=packages.remove');
  });

  it('AC3: no package shows only the install form, first repository selected', async () => {
    const html = await section({ pkg: null });
    expect(html).toContain('Install package');
    expect(html).toMatch(/<option value="other-id"[^>]*selected/);
    expect(html).not.toContain('Replace package');
    expect(html).not.toContain('Remove package');
    expect(html).not.toContain('already started keep');
    expect(html).not.toContain('status mapping');
  });

  it('shows no form when the project has no repository', async () => {
    const html = await section({ pkg: null, repositories: [] });
    expect(html).not.toContain('Install package');
  });

  it('AC5: refusals render inline, the remove one amber', async () => {
    const detail =
      'refused: 2 open initiatives use this package — familio-dessin-v2, familio-chores-v3';
    const html = await section({ pkg, refusal: { install: 'path not found', remove: detail } });
    expect(html).toContain(detail);
    expect(html).toMatch(
      /data-signal="needs-you"[^>]*data-testid="projects-package-remove-refusal"|data-testid="projects-package-remove-refusal"[^>]*data-signal="needs-you"/,
    );
    expect(html).toContain('data-testid="projects-package-install-refusal"');
    expect(html).toContain('path not found');
  });

  it('AC9: unavailable shows only the readout', async () => {
    const html = await section({ pkg: 'unavailable' });
    expect(html).toContain('PACKAGE UNAVAILABLE');
    expect(html).toContain('The list could not be read from backend-api.');
    expect(html).toContain('Reload the page once the connection is restored.');
    expect(html).not.toContain('Install package');
  });
});

describe('projects page package read', () => {
  const detail = {
    id: ID,
    slug: 'first-project',
    name: 'First Project',
    context_text: '',
    context_paths: [],
    env_vars: [],
    log_prompt_content: false,
    created_at: '2026-01-05T09:00:00Z',
    updated_at: '2026-01-06T10:00:00Z',
    repositories: [],
    monthly_spend_usd: null,
  };
  async function page(answer: () => Response | Promise<Response>): Promise<string> {
    vi.stubGlobal(
      'fetch',
      vi.fn((request: Request) => {
        const { pathname } = new URL(request.url);
        if (pathname === '/api/v1/projects') {
          return Promise.resolve(
            new Response(JSON.stringify({ items: [detail], next_cursor: null })),
          );
        }
        if (pathname === `/api/v1/projects/${ID}/package`) return Promise.resolve(answer());
        return Promise.resolve(new Response(JSON.stringify(detail)));
      }),
    );
    return (await container()).renderToString(ProjectsIndexPage, {
      request: new Request(`http://web-client.test/projects?id=${ID}`),
    });
  }

  it('AC3: a 404 reads as no package; section sits between REPOSITORIES and SETTINGS', async () => {
    const html = await page(() => new Response('{}', { status: 404 }));
    expect(html).not.toContain('PACKAGE UNAVAILABLE');
    const at = (s: string) => html.indexOf(s);
    expect(at('REPOSITORIES')).toBeLessThan(at('PACKAGE'));
    expect(at('PACKAGE')).toBeLessThan(at('SETTINGS'));
  });

  it('renders an installed package', async () => {
    const html = await page(() => new Response(JSON.stringify({ ...pkg, repository_id: HUB })));
    expect(html).toContain('rebecamurillo-initiatives');
    expect(html).toContain('Remove package');
  });

  it.each([
    ['a 500', () => new Response('{}', { status: 500 })],
    ['a payload without a sequence', () => new Response('{"name":"x"}')],
    ['a rejected fetch', () => Promise.reject(new Error('down'))],
  ])('AC9: %s reads PACKAGE UNAVAILABLE and the rest renders', async (_n, answer) => {
    const html = await page(answer);
    expect(html).toContain('PACKAGE UNAVAILABLE');
    expect(html).toContain('First Project');
    expect(html).toContain('SETTINGS');
  });
});
