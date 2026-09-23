/**
 * `src/lib/initiative/view.ts` (S7): the pure derivations `InitiativeDetail.tsx` and
 * `src/components/initiative/{MemberRow,RepoSection}.tsx` render a `GET /initiatives/{slug}`
 * response through.
 */
import { describe, expect, it } from 'vitest';

import {
  cancelConfirmText,
  cancelInitiativeBody,
  detailRequestPath,
  golivemembers,
  hasActiveMember,
  hasCancellableMember,
  memberHref,
  memberToken,
  notFoundHeadline,
  repoGroups,
  signalsRequestPath,
  waitsForText,
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
    branch: 'main',
    ...overrides,
  };
}

describe('memberToken', () => {
  it('maps every lifecycle status verbatim', () => {
    expect(memberToken('queued', null)).toBe('QUE');
    expect(memberToken('running', null)).toBe('RUN');
    expect(memberToken('done', null)).toBe('DON');
    expect(memberToken('failed', null)).toBe('ERR');
    expect(memberToken('cancelled', null)).toBe('CAN');
  });

  it('reads a checkpoint park as CHK, and every other park as BLK', () => {
    expect(memberToken('needs_you', 'checkpoint')).toBe('CHK');
    expect(memberToken('needs_you', 'blocked')).toBe('BLK');
    expect(memberToken('needs_you', null)).toBe('BLK');
  });
});

describe('memberHref', () => {
  it('links to the Run detail screen', () => {
    expect(memberHref('run-1')).toBe('/workflows/run-1');
  });
});

describe('repoGroups', () => {
  it('pairs an epic Run with its own merge Run, by shared epic_id and repository', () => {
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
        member({ run_id: 'epic-run', role: 'epic', epic_id: 'epic-a', repository_id: 'repo-1' }),
        member({
          run_id: 'merge-run',
          role: 'merge',
          epic_id: 'epic-a',
          repository_id: 'repo-1',
          template: 'merge',
        }),
      ],
    };

    const groups = repoGroups(view);

    expect(groups).toHaveLength(1);
    expect(groups[0]?.pairs).toHaveLength(1);
    expect(groups[0]?.pairs[0]?.epic?.run_id).toBe('epic-run');
    expect(groups[0]?.pairs[0]?.merge?.run_id).toBe('merge-run');
  });

  it('still pairs an epic with no merge Run yet — the merge slot reads null', () => {
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
      members: [member({ run_id: 'epic-run', role: 'epic', epic_id: 'epic-a' })],
    };

    const groups = repoGroups(view);

    expect(groups[0]?.pairs[0]?.epic?.run_id).toBe('epic-run');
    expect(groups[0]?.pairs[0]?.merge).toBeNull();
  });

  it('answers no groups for no repositories at all', () => {
    expect(repoGroups({ slug: 'demo', repos: [], members: [] })).toEqual([]);
  });
});

describe('golivemembers', () => {
  it('answers only the golive role', () => {
    const view: InitiativeOut = {
      slug: 'demo',
      repos: [],
      members: [
        member({ run_id: 'epic-run', role: 'epic' }),
        member({ run_id: 'golive-run', role: 'golive', epic_id: null }),
      ],
    };

    expect(golivemembers(view).map((m) => m.run_id)).toEqual(['golive-run']);
  });
});

describe('waitsForText', () => {
  it('is null with no edges', () => {
    expect(waitsForText(member({ after_run_ids: [] }), [])).toBeNull();
  });

  it('names the waited-on member’s own epic_id', () => {
    const upstream = member({ run_id: 'epic-a-run', epic_id: 'epic-a' });
    const waiting = member({
      run_id: 'epic-b-run',
      epic_id: 'epic-b',
      after_run_ids: ['epic-a-run'],
    });

    expect(waitsForText(waiting, [upstream, waiting])).toBe('waits for: epic-a');
  });

  it('falls back to the raw run id when the edge names a member not in this read', () => {
    const waiting = member({ after_run_ids: ['missing-run'] });

    expect(waitsForText(waiting, [waiting])).toBe('waits for: missing-run');
  });
});

describe('hasActiveMember', () => {
  it('is true while any member is queued, running or needs_you', () => {
    expect(hasActiveMember({ slug: 'd', repos: [], members: [member({ status: 'queued' })] })).toBe(
      true,
    );
    expect(
      hasActiveMember({ slug: 'd', repos: [], members: [member({ status: 'running' })] }),
    ).toBe(true);
    expect(
      hasActiveMember({ slug: 'd', repos: [], members: [member({ status: 'needs_you' })] }),
    ).toBe(true);
  });

  it('is false once every member is settled', () => {
    expect(
      hasActiveMember({
        slug: 'd',
        repos: [],
        members: [member({ status: 'done' }), member({ status: 'failed' })],
      }),
    ).toBe(false);
    expect(hasActiveMember({ slug: 'd', repos: [], members: [] })).toBe(false);
  });
});

describe('detailRequestPath / notFoundHeadline', () => {
  it('builds the proxy path, url-encoded', () => {
    expect(detailRequestPath('demo slug')).toBe('/api/initiatives/demo%20slug');
  });

  it('states the 404 fact verbatim', () => {
    expect(notFoundHeadline('demo')).toBe('NO INITIATIVE UNDER demo');
  });
});

describe('hasCancellableMember (S8)', () => {
  it('is true while any member is queued, running or needs_you', () => {
    expect(
      hasCancellableMember({ slug: 'd', repos: [], members: [member({ status: 'queued' })] }),
    ).toBe(true);
    expect(
      hasCancellableMember({ slug: 'd', repos: [], members: [member({ status: 'running' })] }),
    ).toBe(true);
    expect(
      hasCancellableMember({ slug: 'd', repos: [], members: [member({ status: 'needs_you' })] }),
    ).toBe(true);
  });

  it('is false once every member is settled', () => {
    expect(
      hasCancellableMember({
        slug: 'd',
        repos: [],
        members: [member({ status: 'done' }), member({ status: 'cancelled' })],
      }),
    ).toBe(false);
    expect(hasCancellableMember({ slug: 'd', repos: [], members: [] })).toBe(false);
  });
});

describe('cancelInitiativeBody / signalsRequestPath / cancelConfirmText (S8)', () => {
  it('posts exactly {kind: cancel}', () => {
    expect(cancelInitiativeBody()).toEqual({ kind: 'cancel' });
  });

  it('builds the proxy signals path, url-encoded', () => {
    expect(signalsRequestPath('demo slug')).toBe('/api/initiatives/demo%20slug/signals');
  });

  it('names the slug and the mechanism, never apologising (NFR-8)', () => {
    const text = cancelConfirmText('q4');
    expect(text).toContain('q4');
    expect(text).toContain('dependents first');
    expect(text.toLowerCase()).not.toContain('sorry');
  });
});
