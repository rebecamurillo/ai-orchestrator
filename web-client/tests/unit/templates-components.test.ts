/**
 * The two static components 3.5 adds, rendered directly with fixture props — `astro/
 * container` pattern from `tests/unit/projects-components.test.ts`.
 *
 * This is also where the cross-Template half of AC1 is proven: `GET /api/v1/templates`
 * stays unconditionally empty in the shared e2e stub (frozen `shell.spec.ts` asserts
 * `NO TEMPLATES` at bare `/templates` against it), so "every version of every Template, with
 * pinned-by and called-by" cannot be shown end to end. `VersionsList` rendered here with
 * fixture rows for two Templates is the layer that proves it instead (the story's Design
 * Notes document the same split for Projects' `ProjectListRow`).
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeAll, describe, expect, it } from 'vitest';

import InputsTable from '../../src/components/templates/InputsTable.astro';
import VersionsList from '../../src/components/templates/VersionsList.astro';
import type { VersionRow } from '../../src/components/templates/version-row';

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

function row(overrides: Partial<VersionRow>): VersionRow {
  return {
    name: 'story',
    version: 1,
    calledBy: [],
    href: '/templates/story/1',
    active: false,
    ...overrides,
  };
}

describe('VersionsList', () => {
  it('renders no rows as the exact voice string, and no list', async () => {
    const html = await render(VersionsList, { rows: [] });

    expect(html).toContain('no template version is stored');
    expect(html).not.toContain('<ul');
  });

  it('states the immutability hint verbatim', async () => {
    const html = await render(VersionsList, { rows: [] });

    expect(html).toContain(
      'a saved version never changes; a version pinned by a run, directly or as a callee, is',
    );
    expect(html).toContain('frozen');
  });

  it('renders every version of every Template, each pinned by 0 runs and read-only', async () => {
    const html = await render(VersionsList, {
      rows: [
        row({ name: 'epic', version: 1, href: '/templates/epic/1' }),
        row({ name: 'story', version: 1, href: '/templates/story/1' }),
        row({ name: 'story', version: 2, href: '/templates/story/2' }),
      ],
    });

    expect(html).toContain('data-testid="templates-version-epic-1"');
    expect(html).toContain('data-testid="templates-version-story-1"');
    expect(html).toContain('data-testid="templates-version-story-2"');
    expect([...html.matchAll(/pinned by 0 runs/g)]).toHaveLength(3);
    expect([...html.matchAll(/read-only/g)]).toHaveLength(3);
  });

  it('names the caller of a callee, and omits the fragment when there is none', async () => {
    const html = await render(VersionsList, {
      rows: [
        row({ name: 'story', version: 1, calledBy: [{ name: 'epic', version: 1, pinned: true }] }),
        row({ name: 'epic', version: 1, href: '/templates/epic/1', calledBy: [] }),
      ],
    });

    expect(html).toContain('called by epic@1 (pinned)');
    const epicRow = html.slice(html.indexOf('templates-version-epic-1'));
    expect(epicRow).not.toContain('called by');
  });

  it('joins multiple callers with a comma', async () => {
    const html = await render(VersionsList, {
      rows: [
        row({
          calledBy: [
            { name: 'epic', version: 1, pinned: true },
            { name: 'initiative', version: 2, pinned: false },
          ],
        }),
      ],
    });

    // Operator decision 2026-10-02 (editable workflows, unpinned callees): each caller is
    // labelled pinned or follows; the previous bare `epic@1, initiative@2` form is retired
    expect(html).toContain('called by epic@1 (pinned), initiative@2 (follows)');
  });

  it('marks the active row, and only the active row', async () => {
    const html = await render(VersionsList, {
      rows: [row({ name: 'story', version: 1, active: true }), row({ name: 'story', version: 2 })],
    });

    expect(html).toMatch(/data-testid="templates-version-story-1"[^>]*data-selected="true"/);
    expect(html).toMatch(/data-testid="templates-version-story-2"[^>]*data-selected="false"/);
  });

  it('links each row to its own version', async () => {
    const html = await render(VersionsList, { rows: [row({ href: '/templates/story/1' })] });

    expect(html).toMatch(/<a[^>]*href="\/templates\/story\/1"/);
  });
});

describe('InputsTable', () => {
  it('renders no inputs as the exact voice string, and no table', async () => {
    const html = await render(InputsTable, { inputs: [] });

    expect(html).toContain('no inputs declared');
    expect(html).not.toContain('<table');
  });

  it('lists every input with its type, required, and default', async () => {
    const html = await render(InputsTable, {
      inputs: [
        { name: 'project', type: 'project', required: true, default: null, values: [] },
        { name: 'harness', type: 'enum', required: false, default: 'claude', values: [] },
      ],
    });

    expect(html).toContain('data-testid="templates-inputs"');
    expect(html).toContain('project');
    expect(html).toMatch(
      /<td[^>]*>project<\/td>\s*<td[^>]*>project<\/td>\s*<td[^>]*>yes<\/td>\s*<td[^>]*>—<\/td>/,
    );
    expect(html).toMatch(
      /<td[^>]*>harness<\/td>\s*<td[^>]*>enum<\/td>\s*<td[^>]*>no<\/td>\s*<td[^>]*>claude<\/td>/,
    );
  });

  it('renders a boolean default as the word, not "1" or ""', async () => {
    const html = await render(InputsTable, {
      inputs: [{ name: 'flag', type: 'string', required: false, default: false, values: [] }],
    });

    expect(html).toMatch(/<td[^>]*>false<\/td>/);
  });
});
