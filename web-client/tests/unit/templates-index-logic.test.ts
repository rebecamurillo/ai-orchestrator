/**
 * `selectRedirectTarget` (3.5, AC1): bare `/templates` redirects to the latest version of
 * the first Template by name. `GET /api/v1/templates` answers unconditionally empty in the
 * shared e2e stub (the story's Design Notes), so the redirect itself cannot be shown end to
 * end — this is the one place it is proven.
 */
import { describe, expect, it } from 'vitest';

import { selectRedirectTarget, type TemplateSummary } from '../../src/lib/templates/index-logic';

function summary(overrides: Partial<TemplateSummary>): TemplateSummary {
  return {
    name: 'template',
    description: null,
    latest_version: 1,
    versions: [1],
    ...overrides,
  };
}

describe('selectRedirectTarget', () => {
  it('returns null for an empty list', () => {
    expect(selectRedirectTarget([])).toBeNull();
  });

  it('picks the first Template by name, not by list order', () => {
    const items = [
      summary({ name: 'story', latest_version: 3 }),
      summary({ name: 'epic', latest_version: 2 }),
    ];

    expect(selectRedirectTarget(items)).toEqual({ name: 'epic', version: 2 });
  });

  it('targets the latest_version field, not the highest entry in versions[]', () => {
    const items = [summary({ name: 'demo', latest_version: 4, versions: [1, 2, 3, 4] })];

    expect(selectRedirectTarget(items)).toEqual({ name: 'demo', version: 4 });
  });

  it('never mutates the array it was given', () => {
    const items = [summary({ name: 'story' }), summary({ name: 'epic' })];
    const copy = [...items];

    selectRedirectTarget(items);

    expect(items).toEqual(copy);
  });
});
