/**
 * `RepositoriesTable.astro`'s `Initialise repository` control (4.10, UX-DR12): the four
 * states its own `initControl` reads off a row's `run` and `methodNeedsInit`. Rendered
 * directly with fixture props, the same `astro/container` pattern
 * `projects-components.test.ts` (2.4) uses for the rest of this component.
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeAll, describe, expect, it } from 'vitest';

import RepositoriesTable from '../../src/components/RepositoriesTable.astro';
import type { RepositoryRow } from '../../src/components/repository-row';

let container: AstroContainer;

beforeAll(async () => {
  container = await AstroContainer.create();
});

function render(props: Record<string, unknown>): Promise<string> {
  return container.renderToString(RepositoriesTable, { props });
}

function row(overrides: Partial<RepositoryRow>): RepositoryRow {
  return {
    id: 'repo-id',
    slug: 'orchestrator-api',
    defaultBranch: 'main',
    method: 'missing',
    qualityGateCommand: '',
    testGlobs: [],
    status: 'ok',
    seconds: 3,
    output: '',
    hint: '',
    verifySkipped: false,
    methodNeedsInit: true,
    run: null,
    ...overrides,
  };
}

describe('Initialise repository control', () => {
  it('offers the button when the method needs it and no Run has ever run', async () => {
    const html = await render({ projectId: 'p1', repositories: [row({})] });

    expect(html).toContain('data-testid="projects-init-orchestrator-api"');
    expect(html).toContain('Initialise repository');
    expect(html).not.toContain('last attempt');
  });

  it('offers no control when the method is already resolved and no Run has ever run', async () => {
    const html = await render({
      projectId: 'p1',
      repositories: [row({ method: '6.11.0', methodNeedsInit: false })],
    });

    expect(html).not.toContain('data-testid="projects-init-orchestrator-api"');
    expect(html).not.toContain('Initialise repository');
  });

  it('links to the Run while it is non-terminal, for every non-terminal token', async () => {
    for (const token of ['QUE', 'RUN', 'BLK', 'CHK'] as const) {
      const html = await render({
        projectId: 'p1',
        repositories: [row({ run: { id: 'run-1', token, reason: '', compareUrl: null } })],
      });

      expect(html).toContain(`initialising · ${token}`);
      expect(html).toContain('href="/workflows/run-1"');
      expect(html).not.toContain('Initialise repository');
    }
  });

  it('reads the version once the method cell has resolved one', async () => {
    const html = await render({
      projectId: 'p1',
      repositories: [
        row({
          method: '6.11.0',
          methodNeedsInit: false,
          run: {
            id: 'run-1',
            token: 'DON',
            reason: '',
            compareUrl: 'https://github.com/acme/widgets/compare/main...chore/bmad-init',
          },
        }),
      ],
    });

    expect(html).toContain('initialised · v6.11.0 ·');
    expect(html).toContain('href="https://github.com/acme/widgets/compare/main...chore/bmad-init"');
  });

  it('reads no version while the method still says missing or outdated', async () => {
    for (const method of ['missing', 'outdated']) {
      const html = await render({
        projectId: 'p1',
        repositories: [
          row({
            method,
            run: { id: 'run-1', token: 'DON', reason: '', compareUrl: 'https://example/compare' },
          }),
        ],
      });

      expect(html).toContain('initialised ·');
      expect(html).not.toContain('initialised · v');
    }
  });

  it('offers the button again with the last attempt line for a failed Run', async () => {
    const html = await render({
      projectId: 'p1',
      repositories: [
        row({
          run: { id: 'run-1', token: 'ERR', reason: 'install failed: exit 1', compareUrl: null },
        }),
      ],
    });

    expect(html).toContain('Initialise repository');
    expect(html).toContain('last attempt ERR · install failed: exit 1');
  });

  it('offers the button again with the last attempt line for a cancelled Run', async () => {
    const html = await render({
      projectId: 'p1',
      repositories: [
        row({
          run: { id: 'run-1', token: 'CAN', reason: 'cancelled by the operator', compareUrl: null },
        }),
      ],
    });

    expect(html).toContain('Initialise repository');
    expect(html).toContain('last attempt CAN · cancelled by the operator');
  });

  it('renders nothing for a terminal Run with no compare url and a resolved method', async () => {
    const html = await render({
      projectId: 'p1',
      repositories: [
        row({
          method: '6.11.0',
          methodNeedsInit: false,
          run: { id: 'run-1', token: 'DON', reason: '', compareUrl: null },
        }),
      ],
    });

    expect(html).not.toContain('Initialise repository');
    expect(html).not.toContain('initialised ·');
    expect(html).not.toContain('initialising ·');
  });
});
