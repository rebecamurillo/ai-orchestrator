/**
 * `harnessProbeLineText()` and the `ProbeResultOut` type export (story 2-3, probe-based
 * row text in HarnessList).
 */
import { describe, expect, it } from 'vitest';

import { harnessProbeLineText } from '../../src/lib/newwf/state';
import type { ProbeResultOut } from '../../src/lib/newwf/state';
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

describe('harnessProbeLineText', () => {
  it('renders ok result with name, "ok", and last readiness time from harness SSR data', () => {
    const h = harness({ last_readiness_at: '2026-09-17T10:30:00Z' });
    const result: ProbeResultOut = {
      ok: true,
      failing_reason: null,
      models: ['m1'],
      version: 'v1',
    };

    expect(harnessProbeLineText(h, result)).toBe(
      'claude · ok · last readiness 2026-09-17 10:30:00 · ',
    );
  });

  it('renders failing result with failing_reason and dash when no last readiness', () => {
    const h = harness(); // last_readiness_at: null
    const result: ProbeResultOut = {
      ok: false,
      failing_reason: 'not logged in',
      models: [],
      version: '',
    };

    expect(harnessProbeLineText(h, result)).toBe('claude · not logged in · last readiness — · ');
  });

  it('falls back to "probe failed" when ok is false and failing_reason is null', () => {
    const h = harness();
    const result: ProbeResultOut = { ok: false, failing_reason: null, models: [], version: '' };

    expect(harnessProbeLineText(h, result)).toBe('claude · probe failed · last readiness — · ');
  });

  it('ProbeResultOut is exported from state.ts and usable as a type annotation', () => {
    const r: ProbeResultOut = { ok: true, failing_reason: null, models: [], version: 'v1' };

    expect(r.ok).toBe(true);
  });
});
