/**
 * `src/lib/initiative/preflight.ts` (S7): the pure derivations `RepoTable.tsx`/`EpicList.tsx`
 * render an `InitiativePreflightOut` through.
 */
import { describe, expect, it } from 'vitest';

import {
  branchStateText,
  epicsByRepository,
  listText,
  orDash,
  orderText,
} from '../../src/lib/initiative/preflight';
import type { components } from '../../src/api/schema';

type EpicPreflightOut = components['schemas']['EpicPreflightOut'];

function epic(overrides: Partial<EpicPreflightOut> = {}): EpicPreflightOut {
  return {
    epic_id: 'epic-a',
    title: 'Epic A',
    repository_id: 'repo-1',
    repository: 'repo-one',
    branch: 'epics/epic-a',
    working_branch: 'epics/epic-a',
    depends_on: [],
    checkpoint: null,
    lines: [],
    ...overrides,
  };
}

describe('branchStateText', () => {
  it('reads adopted when the remote already holds the branch, created otherwise', () => {
    expect(branchStateText(true)).toBe('adopted');
    expect(branchStateText(false)).toBe('created');
  });
});

describe('listText', () => {
  it('joins a non-empty list, and dashes an empty one', () => {
    expect(listText(['a', 'b'])).toBe('a, b');
    expect(listText([])).toBe('—');
  });
});

describe('orDash', () => {
  it('dashes null, states a real value verbatim', () => {
    expect(orDash(null)).toBe('—');
    expect(orDash('spec_review')).toBe('spec_review');
  });
});

describe('orderText', () => {
  it('arrows a non-empty order, and dashes an empty one (a cycle refusal)', () => {
    expect(orderText(['epic-a', 'epic-b'])).toBe('epic-a → epic-b');
    expect(orderText([])).toBe('—');
  });
});

describe('epicsByRepository', () => {
  it('groups epics by repository, in the order[] sequence', () => {
    const epics = [
      epic({ epic_id: 'epic-b', repository_id: 'repo-2', repository: 'repo-two' }),
      epic({ epic_id: 'epic-a', repository_id: 'repo-1', repository: 'repo-one' }),
    ];

    const groups = epicsByRepository(epics, ['epic-a', 'epic-b']);

    expect(groups.map((g) => g.repositoryId)).toEqual(['repo-1', 'repo-2']);
    expect(groups[0]?.epics.map((e) => e.epic_id)).toEqual(['epic-a']);
    expect(groups[1]?.epics.map((e) => e.epic_id)).toEqual(['epic-b']);
  });

  it('appends an epic order[] does not name after every epic it does name', () => {
    const epics = [epic({ epic_id: 'epic-a' }), epic({ epic_id: 'epic-orphan' })];

    const groups = epicsByRepository(epics, ['epic-a']);

    expect(groups[0]?.epics.map((e) => e.epic_id)).toEqual(['epic-a', 'epic-orphan']);
  });

  it('groups a null repository_id under its own trailing group', () => {
    const epics = [
      epic({ epic_id: 'epic-a', repository_id: 'repo-1', repository: 'repo-one' }),
      epic({ epic_id: 'epic-none', repository_id: null, repository: null }),
    ];

    const groups = epicsByRepository(epics, ['epic-a', 'epic-none']);

    expect(groups).toHaveLength(2);
    expect(groups[1]?.repositoryId).toBeNull();
    expect(groups[1]?.epics.map((e) => e.epic_id)).toEqual(['epic-none']);
  });

  it('answers no groups for no epics at all', () => {
    expect(epicsByRepository([], [])).toEqual([]);
  });
});
