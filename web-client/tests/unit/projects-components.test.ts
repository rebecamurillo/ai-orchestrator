/**
 * The three static components 2.4 adds, rendered directly with fixture props rather than
 * through the e2e stub — `astro/container` pattern from `components.test.ts`.
 *
 * This is also where the list-population half of the brief's combined AC is proven: the
 * shared e2e stub's `GET /api/v1/projects` must stay unconditionally empty for the frozen
 * `shell.spec.ts` (see the story's Design Notes), so "two rows render, one selected" cannot
 * be shown end to end. `ProjectListRow` rendered twice with fixture props is the layer that
 * proves it instead.
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeAll, describe, expect, it } from 'vitest';

import ProjectListRow from '../../src/components/ProjectListRow.astro';
import ProjectSettings from '../../src/components/ProjectSettings.astro';
import RepositoriesTable from '../../src/components/RepositoriesTable.astro';
import type { RepositoryRow } from '../../src/components/repository-row';

let container: AstroContainer;

beforeAll(async () => {
  container = await AstroContainer.create();
});

function render(
  component: Parameters<AstroContainer['renderToString']>[0],
  props: Record<string, unknown>,
): Promise<string> {
  return container.renderToString(component, { props });
}

function row(overrides: Partial<RepositoryRow>): RepositoryRow {
  return {
    id: 'repo-id',
    slug: 'orchestrator-api',
    defaultBranch: 'main',
    method: '6.11.0',
    qualityGateCommand: 'make lint && make test',
    testGlobs: ['tests/**/*.test.ts'],
    status: 'ok',
    seconds: 12,
    output: '',
    hint: '',
    verifySkipped: false,
    ...overrides,
  };
}

describe('RepositoriesTable', () => {
  it('renders no repositories as the exact voice string, and no table', async () => {
    const html = await render(RepositoriesTable, {
      projectId: 'project-id',
      repositories: [],
    });

    expect(html).toContain('no repositories · edit the project to add one');
    expect(html).not.toContain('<table');
  });

  it('sums the clone-check line seconds onto the ok cell', async () => {
    const html = await render(RepositoriesTable, {
      projectId: 'project-id',
      repositories: [row({ status: 'ok', seconds: 15 })],
    });

    expect(html).toContain('ok · 15s');
    expect(html).not.toContain('data-signal="failed"');
  });

  it('colours only the failed clone-check cell, and offers the recheck form and output', async () => {
    const html = await render(RepositoriesTable, {
      projectId: 'project-id',
      repositories: [
        row({
          slug: 'orchestrator-web',
          status: 'failed',
          output: 'fatal: could not read Username',
          hint: 'add a deploy key',
        }),
      ],
    });

    expect(html).toContain('failed · new runs blocked');
    expect(html).toMatch(/<td data-signal="failed"[^>]*>failed · new runs blocked<\/td>/);
    expect(html).toContain('fatal: could not read Username');
    expect(html).toContain('add a deploy key');
    expect(html).toContain('data-testid="projects-repo-orchestrator-web"');
    expect(html).toContain('data-testid="projects-recheck-orchestrator-web"');
    expect(html).toContain('re-run check');
  });

  it('reads pending as save to check, with no colour', async () => {
    const html = await render(RepositoriesTable, {
      projectId: 'project-id',
      repositories: [row({ status: 'pending', seconds: 0 })],
    });

    expect(html).toContain('pending · save to check');
    expect(html).not.toContain('data-signal="failed"');
  });

  it('shows the stored method string verbatim, and an em dash only when it is null', async () => {
    const html = await render(RepositoriesTable, {
      projectId: 'project-id',
      repositories: [
        row({ slug: 'a', method: 'missing' }),
        row({ slug: 'b', method: 'outdated' }),
        row({ slug: 'c', method: '—' }),
      ],
    });

    expect(html).toContain('>missing<');
    expect(html).toContain('>outdated<');
    expect(html).toContain('>—<');
  });

  it('reads an undeclared quality gate and test globs as none declared', async () => {
    const html = await render(RepositoriesTable, {
      projectId: 'project-id',
      repositories: [row({ qualityGateCommand: '', testGlobs: [] })],
    });

    expect([...html.matchAll(/— none declared/g)]).toHaveLength(2);
  });

  it('marks a skipped verify step, and a present one as ready', async () => {
    const html = await render(RepositoriesTable, {
      projectId: 'project-id',
      repositories: [
        row({ slug: 'skipped-one', verifySkipped: true }),
        row({ slug: 'ready-one', verifySkipped: false }),
      ],
    });

    expect(html).toContain('verify step will be skipped');
    expect(html).toContain('>ready<');
  });
});

describe('ProjectSettings', () => {
  it('counts the env vars and lists each masked value', async () => {
    const html = await render(ProjectSettings, {
      envVars: [
        { name: 'NODE_ENV', masked: '****ion' },
        { name: 'PORT', masked: '****4321' },
      ],
    });

    expect(html).toContain('env vars');
    expect(html).toContain('2 · NODE_ENV ****ion, PORT ****4321');
    expect(html).toContain('GitHub token and gateway key');
    expect(html).toContain('instance settings');
  });

  it('reads no env vars as the exact voice string', async () => {
    const html = await render(ProjectSettings, { envVars: [] });

    expect(html).toContain('0 · none set');
  });
});

describe('ProjectListRow', () => {
  const base = {
    id: 'p1',
    slug: 'mixed-signals',
    name: 'Mixed Signals',
    repositoryCount: 4,
    failedCount: 0,
    selected: false,
    href: '/projects?id=p1',
  };

  it('renders the row copy, the test-id, and the link target', async () => {
    const html = await render(ProjectListRow, base);

    expect(html).toContain('data-testid="projects-row-mixed-signals"');
    expect(html).toMatch(/<a[^>]*href="\/projects\?id=p1"/);
    expect(html).toContain('Mixed Signals');
    expect(html).toContain('4 repositories · 0 runs');
  });

  it('renders no failed fragment at all when nothing failed', async () => {
    const html = await render(ProjectListRow, base);

    expect(html).not.toContain('failed');
  });

  it('renders the failed count only when it is non-zero', async () => {
    const html = await render(ProjectListRow, { ...base, failedCount: 2 });

    expect(html).toContain('2 failed');
  });

  it('marks the selected row, and only the selected row, across two renders', async () => {
    const selected = await render(ProjectListRow, { ...base, selected: true });
    const unselected = await render(ProjectListRow, { ...base, id: 'p2', selected: false });

    expect(selected).toContain('data-selected="true"');
    expect(unselected).toContain('data-selected="false"');
  });
});
