/**
 * `src/lib/initiative/badge.ts` (S7): the initiative badge `Header.tsx` renders on a Run
 * detail's headline once the Run carries `initiative` — reads only the two stored fields,
 * never a Template name (S7's own rule).
 */
import { describe, expect, it } from 'vitest';

import { initiativeBadgeText, initiativeHref } from '../../src/lib/initiative/badge';

describe('initiativeBadgeText', () => {
  it('is null for a Run with no initiative at all', () => {
    expect(initiativeBadgeText({})).toBeNull();
    expect(initiativeBadgeText({ initiative: null })).toBeNull();
    expect(initiativeBadgeText({ initiative: '' })).toBeNull();
  });

  it('is "{slug} · {role}" once the Run carries both', () => {
    expect(initiativeBadgeText({ initiative: 'demo', initiative_role: 'epic' })).toBe(
      'demo · epic',
    );
  });

  it('dashes the role when the slug is set but the role is not', () => {
    expect(initiativeBadgeText({ initiative: 'demo', initiative_role: null })).toBe('demo · —');
    expect(initiativeBadgeText({ initiative: 'demo' })).toBe('demo · —');
  });
});

describe('initiativeHref', () => {
  it('links to the initiative detail screen, url-encoded', () => {
    expect(initiativeHref('demo slug')).toBe('/workflows/initiative/demo%20slug');
  });
});
