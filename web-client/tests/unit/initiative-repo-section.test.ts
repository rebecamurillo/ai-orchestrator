/**
 * `RepoSection.tsx` (S7) — stateless, `RunCard.tsx`'s own `renderToStaticMarkup` precedent.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RepoSection from '../../src/components/initiative/RepoSection';
import {
  repoGroups,
  type InitiativeMemberOut,
  type InitiativeOut,
} from '../../src/lib/initiative/view';

function member(overrides: Partial<InitiativeMemberOut> = {}): InitiativeMemberOut {
  return {
    run_id: 'run-1',
    epic_id: 'epic-a',
    role: 'epic',
    repository_id: 'repo-1',
    status: 'running',
    park_kind: null,
    park_reason: null,
    after_run_ids: [],
    template: 'epic',
    branch: 'epics/epic-a',
    ...overrides,
  };
}

describe('RepoSection', () => {
  it('renders the repository head, its integration branch, and each epic/merge pair', () => {
    const view: InitiativeOut = {
      slug: 'demo',
      repos: [
        {
          repository_id: 'repo-1',
          repository: 'repo-one',
          url: 'https://example.com/repo-one',
          default_branch: 'main',
          branch: 'integration/demo',
        },
      ],
      members: [
        member({ run_id: 'epic-run', role: 'epic' }),
        member({ run_id: 'merge-run', role: 'merge', template: 'merge' }),
      ],
    };
    const group = repoGroups(view)[0]!;

    const markup = renderToStaticMarkup(
      createElement(RepoSection, { group, members: view.members }),
    );

    expect(markup).toContain('data-testid="newin-detail-repo-repo-1"');
    expect(markup).toContain('repo-one');
    expect(markup).toContain('integration/demo');
    expect(markup).toContain('data-testid="newin-detail-pair-epic-a"');
    expect(markup).toContain('data-testid="newin-member-epic-run"');
    expect(markup).toContain('data-testid="newin-member-merge-run"');
  });

  it('states plainly when a repository holds no epic at all', () => {
    const group = {
      repositoryId: 'repo-1',
      repository: 'repo-one',
      url: 'https://example.com/repo-one',
      defaultBranch: 'main',
      branch: null,
      pairs: [],
    };

    const markup = renderToStaticMarkup(createElement(RepoSection, { group, members: [] }));

    expect(markup).toContain('no epic in this repository');
  });
});
