/**
 * `runBody` — empty budget field: body is not null; `budget_usd` is null (story 3-2, AC5).
 */
import { describe, expect, it } from 'vitest';

import { defaultFormState, runBody } from '../../src/lib/newwf/state';

describe('runBody with empty budget', () => {
  const templates = [
    { name: 'initiative', description: null, latest_version: 2, versions: [1, 2] },
  ];

  it('returns a valid body (not null) when budget is empty and other required fields are set', () => {
    const state = {
      ...defaultFormState(),
      projectId: 'p1',
      repositoryId: 'r1',
      baseBranch: 'main',
      budgetUsd: '',
    };

    const body = runBody(state, templates);
    expect(body).not.toBeNull();
  });

  it('sets budget_usd to null in the body when budget is empty', () => {
    const state = {
      ...defaultFormState(),
      projectId: 'p1',
      repositoryId: 'r1',
      baseBranch: 'main',
      budgetUsd: '',
    };

    const body = runBody(state, templates);
    expect(body?.budget_usd).toBeNull();
  });
});
