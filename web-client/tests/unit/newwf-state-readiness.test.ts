/**
 * `readinessBadgeText` helper (story 2-4): pure formatter for the note span beside each
 * harness's "re-run readiness" link.
 */
import { describe, expect, it } from 'vitest';

import { readinessBadgeText } from '../../src/lib/newwf/state';
import type { components } from '../../src/api/schema';

type HarnessOut = components['schemas']['HarnessOut'];

function harness(overrides: Partial<HarnessOut> = {}): HarnessOut {
  return {
    name: 'claude',
    enabled: false,
    last_readiness_at: null,
    failing_check: null,
    version_pin: '2.1.258',
    ...overrides,
  };
}

describe('readinessBadgeText', () => {
  it('returns empty string when both last_readiness_at and failing_check are null', () => {
    expect(readinessBadgeText(harness())).toBe('');
  });

  it('returns formatted time when last_readiness_at is set and failing_check is null', () => {
    expect(readinessBadgeText(harness({ last_readiness_at: '2026-09-17T10:00:00Z' }))).toBe(
      '2026-09-17 10:00:00',
    );
  });

  it('returns just failing_check when last_readiness_at is null', () => {
    expect(readinessBadgeText(harness({ failing_check: 'harness: not running' }))).toBe(
      'harness: not running',
    );
  });

  it('joins time and failing_check with " · " when both are set', () => {
    expect(
      readinessBadgeText(
        harness({
          last_readiness_at: '2026-09-17T10:00:00Z',
          failing_check: 'harness: not running',
        }),
      ),
    ).toBe('2026-09-17 10:00:00 · harness: not running');
  });

  it('handles pin-changed message with no last_readiness_at', () => {
    expect(
      readinessBadgeText(harness({ failing_check: 'version pin changed: 2.1.258 → 2.1.260' })),
    ).toBe('version pin changed: 2.1.258 → 2.1.260');
  });
});
