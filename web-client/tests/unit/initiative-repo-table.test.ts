/**
 * `RepoTable.tsx` (S7) — stateless, `PlanTable.tsx`'s own `renderToStaticMarkup` precedent.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RepoTable from '../../src/components/initiative/RepoTable';
import type { components } from '../../src/api/schema';

type InitiativeRepoOut = components['schemas']['InitiativeRepoOut'];

const repo: InitiativeRepoOut = {
  repository_id: 'repo-1',
  repository: 'repo-one',
  branch: 'integration/demo',
  default_branch: 'main',
  remote_holds_branch: true,
};

describe('RepoTable', () => {
  it('renders the empty reading with no repository resolved', () => {
    const markup = renderToStaticMarkup(createElement(RepoTable, { repos: [] }));

    expect(markup).toContain('data-testid="newin-repos-empty"');
  });

  it('renders one row per repository, adopted/created stated as a word', () => {
    const markup = renderToStaticMarkup(
      createElement(RepoTable, {
        repos: [repo, { ...repo, repository_id: 'repo-2', remote_holds_branch: false }],
      }),
    );

    expect(markup).toContain('data-testid="newin-repo-repo-1"');
    expect(markup).toContain('adopted');
    expect(markup).toContain('data-testid="newin-repo-repo-2"');
    expect(markup).toContain('created');
    expect(markup).toContain('integration/demo');
  });
});
