/**
 * `ProjectListRow` count rendering — priority logic (story 8-6).
 *
 * `projects-components.test.ts` is frozen (root AGENTS.md hard rule 1); these are new
 * assertions for the updated component contract. The frozen tests keep passing because
 * `needsYouCount` defaults to 0 via destructuring, so the priority falls through to
 * show `failedCount` exactly as before.
 */

import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeAll, describe, expect, it } from 'vitest';

import ProjectListRow from '../../src/components/ProjectListRow.astro';

let container: AstroContainer;

beforeAll(async () => {
  container = await AstroContainer.create();
});

function render(props: Record<string, unknown>): Promise<string> {
  return container.renderToString(ProjectListRow, { props });
}

const base = {
  id: 'p1',
  slug: 'my-project',
  name: 'My Project',
  repositoryCount: 2,
  failedCount: 0,
  selected: false,
  href: '/projects/p1/edit',
};

describe('ProjectListRow count priority', () => {
  it('shows "need you" amber when needsYouCount > 0', async () => {
    const html = await render({ ...base, needsYouCount: 2, failedCount: 0 });

    expect(html).toContain('2 need you');
    expect(html).not.toContain('failed');
  });

  it('shows "failed" red when needsYouCount is 0 and failedCount > 0', async () => {
    const html = await render({ ...base, needsYouCount: 0, failedCount: 1 });

    expect(html).toContain('1 failed');
    expect(html).not.toContain('need you');
  });

  it('shows only "need you" amber when both counts are > 0 (priority rule)', async () => {
    const html = await render({ ...base, needsYouCount: 3, failedCount: 2 });

    expect(html).toContain('3 need you');
    expect(html).not.toContain('failed');
  });

  it('shows no colour element when both counts are 0', async () => {
    const html = await render({ ...base, needsYouCount: 0, failedCount: 0 });

    expect(html).not.toContain('need you');
    expect(html).not.toContain('failed');
  });

  it('defaults needsYouCount to 0 when prop is omitted', async () => {
    // Existing frozen test shape: no needsYouCount prop — must not crash and must
    // fall through to failedCount rendering.
    const html = await render({ ...base, failedCount: 2 });

    expect(html).toContain('2 failed');
    expect(html).not.toContain('need you');
  });
});
