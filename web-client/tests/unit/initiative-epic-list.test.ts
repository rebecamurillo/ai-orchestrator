/**
 * `EpicList.tsx` (S7) — stateless, `PlanTable.tsx`'s own `renderToStaticMarkup` precedent.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import EpicList from '../../src/components/initiative/EpicList';
import type { components } from '../../src/api/schema';

type EpicPreflightOut = components['schemas']['EpicPreflightOut'];

const epic: EpicPreflightOut = {
  epic_id: 'epic-a',
  title: 'Epic A',
  repository_id: 'repo-1',
  repository: 'repo-one',
  branch: 'epics/epic-a',
  working_branch: 'epics/epic-a',
  depends_on: ['epic-z'],
  checkpoint: 'spec_review',
  lines: [{ check: 'origin reachable', status: 'ok', text: 'origin ok', fix: null }],
};

describe('EpicList', () => {
  it('renders the empty reading with no epic resolved', () => {
    const markup = renderToStaticMarkup(createElement(EpicList, { epics: [], order: [] }));

    expect(markup).toContain('data-testid="newin-epics-empty"');
  });

  it('groups by repository and shows id, title, depends_on, checkpoint and working branch', () => {
    const markup = renderToStaticMarkup(
      createElement(EpicList, { epics: [epic], order: ['epic-a'] }),
    );

    expect(markup).toContain('data-testid="newin-epic-epic-a"');
    expect(markup).toContain('Epic A');
    expect(markup).toContain('depends on epic-z');
    expect(markup).toContain('checkpoint spec_review');
    expect(markup).toContain('working branch epics/epic-a');
    expect(markup).toContain('repo-one');
  });

  it('dashes an epic with no dependency and no checkpoint', () => {
    const markup = renderToStaticMarkup(
      createElement(EpicList, {
        epics: [{ ...epic, depends_on: [], checkpoint: null, working_branch: null }],
        order: ['epic-a'],
      }),
    );

    expect(markup).toContain('depends on —');
    expect(markup).toContain('checkpoint —');
    expect(markup).toContain('working branch —');
  });

  it('prints each line, the failed word carrying the signal', () => {
    const markup = renderToStaticMarkup(
      createElement(EpicList, {
        epics: [
          {
            ...epic,
            lines: [
              { check: 'origin reachable', status: 'fail', text: 'origin unreachable', fix: null },
            ],
          },
        ],
        order: ['epic-a'],
      }),
    );

    expect(markup).toContain('origin reachable');
    expect(markup).toContain('origin unreachable');
    expect(markup).toContain('data-signal="failed"');
  });
});
