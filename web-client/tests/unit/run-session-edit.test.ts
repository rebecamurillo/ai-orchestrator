/**
 * Story 2-4 review: the artifact modal's Edit is withheld while a senior session holds the
 * Run, as it is during a terminal session (`PUT /runs/{id}/files` is refused either way).
 */
import { describe, expect, it } from 'vitest';

import { canEditFile } from '../../src/lib/run/artifacts';
import type { RunDetailOut } from '../../src/lib/run/detail';

function run(over: Record<string, unknown> = {}): RunDetailOut['run'] {
  return { status: 'needs_you', terminal_session: false, ...over } as RunDetailOut['run'];
}

describe('canEditFile under a senior session', () => {
  it('offers Edit on a parked Run with no session', () => {
    expect(canEditFile(run(), 'specs/x/SPEC.md', 'specs/x')).toBe(true);
  });

  it('withholds Edit while a senior session is open', () => {
    expect(canEditFile(run({ senior_session: true }), 'specs/x/SPEC.md', 'specs/x')).toBe(false);
  });

  it('reads an absent flag as no session', () => {
    expect(canEditFile(run({ senior_session: undefined }), 'specs/x/SPEC.md', 'specs/x')).toBe(
      true,
    );
  });
});
