/**
 * `CloneCheckReadout.astro` (2.5): the **CLONE CHECK** column, rendered straight from a
 * `RepositoryOut[]` with no fetch and no derivation beyond what the story's binding rules
 * name. `AstroContainer` renders it server-side to a string, the same pattern
 * `component-props.test.ts` uses for `Button`/`EmptyState`.
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeAll, describe, expect, it } from 'vitest';

import CloneCheckReadout from '../../src/components/projects/CloneCheckReadout.astro';

let container: AstroContainer;

beforeAll(async () => {
  container = await AstroContainer.create();
});

function render(repositories: unknown[]): Promise<string> {
  return container.renderToString(CloneCheckReadout, { props: { repositories } });
}

const CREATED_AT = '2026-01-05T09:00:00Z';
const UPDATED_AT = '2026-01-06T10:00:00Z';

function repository(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    id: 'repo-id',
    project_id: 'project-id',
    slug: 'orchestrator-api',
    url: 'https://github.com/example/repo.git',
    default_branch: 'main',
    install_command: 'pnpm install',
    quality_gate_command: 'pnpm lint && pnpm test',
    unit_test_command: 'pnpm test',
    test_globs: ['tests/**'],
    package_manager: 'pnpm',
    clone_check: { status: 'pending', at: null, output: '', bmad_version: null },
    clone_check_lines: [],
    clone_check_hint: '',
    verify_skipped: false,
    created_at: CREATED_AT,
    updated_at: UPDATED_AT,
    ...overrides,
  };
}

describe('no repositories yet', () => {
  it('reads "save to run the clone check"', async () => {
    const html = await render([]);

    expect(html).toContain('save to run the clone check');
  });
});

describe('a fully ok repository', () => {
  it('names the slug and all four lines, and ends with "ok"', async () => {
    const html = await render([
      repository({
        slug: 'orchestrator-api',
        clone_check: {
          status: 'ok',
          at: '2026-09-04T12:00:00Z',
          output: 'cloned ok',
          bmad_version: '6.11.0',
        },
        clone_check_lines: [
          { name: 'ls-remote', status: 'ok', seconds: 1, output: 'ok' },
          { name: 'clone', status: 'ok', seconds: 4, output: 'cloned 1234 bytes' },
          { name: 'default branch', status: 'ok', seconds: 0.5, output: 'ok' },
          { name: 'method version', status: 'ok', seconds: 0.1, output: 'ok' },
        ],
      }),
    ]);

    expect(html).toMatch(/data-testid="projects-clone-check-orchestrator-api"/);
    expect(html).toContain('orchestrator-api');
    expect(html).toContain('ls-remote');
    expect(html).toContain('clone');
    // the byte-count text `run_clone_check` (2.3) already put in the line's own `output`
    // reaches the Operator here, not just inside the failed-detail block
    expect(html).toMatch(/clone[\s\S]*?ok[\s\S]*?cloned 1234 bytes[\s\S]*?4s/);
    expect(html).toContain('default branch');
    expect(html).toContain('method version');
    expect(html).not.toContain('run Initialise repository after save');
    expect(html).not.toContain('verify step will be skipped');
    expect(html).toMatch(/class="overall"[^>]*>\s*ok/);
  });
});

describe('a repository the token cannot reach', () => {
  it('shows only the lines that ran, the verbatim output, the hint, and the failed footer', async () => {
    const html = await render([
      repository({
        slug: 'orchestrator-web',
        clone_check: {
          status: 'failed',
          at: '2026-09-04T12:05:00Z',
          output:
            'fatal: could not read Username for https://github.com: terminal prompts disabled',
          bmad_version: null,
        },
        clone_check_lines: [
          {
            name: 'ls-remote',
            status: 'failed',
            seconds: 2,
            output: 'fatal: could not read Username',
          },
        ],
        clone_check_hint: 'add a deploy key or a GITHUB_TOKEN with access to this repository',
      }),
    ]);

    expect(html).toContain('ls-remote');
    expect(html).not.toContain('default branch');
    expect(html).not.toContain('method version');
    expect(html).toContain('fatal: could not read Username for https://github.com');
    expect(html).toContain('add a deploy key or a GITHUB_TOKEN with access to this repository');
    expect(html).toContain('failed · new runs blocked');
    expect(html).toMatch(/data-signal="failed"[^>]*>\s*failed/);
  });
});

describe('a missing or outdated method version', () => {
  it.each(['missing', 'outdated'])(
    'adds "run Initialise repository after save" for %s',
    async (version) => {
      const html = await render([
        repository({
          clone_check: {
            status: 'ok',
            at: '2026-09-04T12:00:00Z',
            output: 'cloned ok',
            bmad_version: version,
          },
          clone_check_lines: [{ name: 'method version', status: 'ok', seconds: 0.1, output: 'ok' }],
        }),
      ]);

      expect(html).toContain('run Initialise repository after save');
    },
  );
});

describe('a repository with no quality_gate_command', () => {
  it('ends with "verify step will be skipped"', async () => {
    const html = await render([repository({ verify_skipped: true })]);

    expect(html).toContain('verify step will be skipped');
  });
});

describe('a pending repository (never checked)', () => {
  it('reads "pending · save to check", the same copy RepositoriesTable.astro (2.4) ships', async () => {
    const html = await render([
      repository({
        clone_check: { status: 'pending', at: null, output: '', bmad_version: null },
        clone_check_lines: [],
      }),
    ]);

    expect(html).toContain('pending · save to check');
    expect(html).not.toContain('data-signal="failed"');
  });
});

describe('signal rule', () => {
  it('paints no failed signal anywhere when the check is ok', async () => {
    const html = await render([
      repository({
        clone_check: {
          status: 'ok',
          at: '2026-09-04T12:00:00Z',
          output: 'cloned ok',
          bmad_version: '6.11.0',
        },
        clone_check_lines: [{ name: 'ls-remote', status: 'ok', seconds: 1, output: 'ok' }],
      }),
    ]);

    expect(html).not.toContain('data-signal="failed"');
  });
});
