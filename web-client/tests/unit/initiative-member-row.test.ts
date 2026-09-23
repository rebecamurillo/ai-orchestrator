/**
 * `MemberRow.tsx` (S7) — stateless, `RunCard.tsx`'s own `renderToStaticMarkup` precedent.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import MemberRow from '../../src/components/initiative/MemberRow';
import type { InitiativeMemberOut } from '../../src/lib/initiative/view';

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

describe('MemberRow', () => {
  it('renders the token, role and a link to the Run detail screen', () => {
    const markup = renderToStaticMarkup(
      createElement(MemberRow, { member: member(), members: [] }),
    );

    expect(markup).toContain('data-testid="newin-member-run-1"');
    expect(markup).toContain('>RUN<');
    expect(markup).toContain('>epic<');
    expect(markup).toContain('href="/workflows/run-1"');
  });

  it('shows the park kind and reason once the member is parked', () => {
    const markup = renderToStaticMarkup(
      createElement(MemberRow, {
        member: member({ status: 'needs_you', park_kind: 'blocked', park_reason: 'no story file' }),
        members: [],
      }),
    );

    expect(markup).toContain('data-testid="newin-member-run-1-park"');
    expect(markup).toContain('blocked');
    expect(markup).toContain('no story file');
  });

  it('renders no park line at all while not parked', () => {
    const markup = renderToStaticMarkup(
      createElement(MemberRow, { member: member(), members: [] }),
    );

    expect(markup).not.toContain('newin-member-run-1-park');
  });

  it('renders the waits-for line once the member has an edge', () => {
    const upstream = member({ run_id: 'up', epic_id: 'epic-z' });
    const waiting = member({ after_run_ids: ['up'] });

    const markup = renderToStaticMarkup(
      createElement(MemberRow, { member: waiting, members: [upstream, waiting] }),
    );

    expect(markup).toContain('waits for: epic-z');
  });

  it('dashes a member with no role at all', () => {
    const markup = renderToStaticMarkup(
      createElement(MemberRow, { member: member({ role: null }), members: [] }),
    );

    expect(markup).toContain('>—<');
  });
});
