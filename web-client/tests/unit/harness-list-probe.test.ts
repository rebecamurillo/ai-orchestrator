/**
 * `HarnessList` with the `probeResults` prop (story 2-3, probe-based harness gating).
 *
 * Unit-test path: renders with `renderToStaticMarkup` in `environment: 'node'`,
 * the same pattern as `harness-list.test.ts`.  The `probeResults !== undefined` guard in the
 * component is what allows the existing `harness-list.test.ts` assertions to pass unchanged —
 * when no prop is passed the fallback to `harness.enabled` applies and this file does not need
 * to re-prove that branch.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import HarnessList from '../../src/components/HarnessList';
import type { components } from '../../src/api/schema';

type HarnessOut = components['schemas']['HarnessOut'];
type ProbeResultOut = components['schemas']['ProbeResultOut'];

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

function probeOk(): ProbeResultOut {
  return { ok: true, failing_reason: null, models: ['claude-opus-4'], version: 'v1.2.3' };
}

function probeFail(reason = 'not logged in'): ProbeResultOut {
  return { ok: false, failing_reason: reason, models: [], version: '' };
}

function render(harnesses: HarnessOut[], probeResults?: Record<string, ProbeResultOut>): string {
  return renderToStaticMarkup(
    createElement(HarnessList, {
      harnesses,
      selected: '',
      onSelect: () => {},
      probeResults,
    }),
  );
}

describe('HarnessList with probeResults prop', () => {
  it('does not disable the radio when probe result is ok', () => {
    const markup = render([harness()], { claude: probeOk() });

    expect(markup).not.toContain('disabled=""');
  });

  it('shows "ok" in the row text when probe result is ok', () => {
    const markup = render([harness()], { claude: probeOk() });

    expect(markup).toContain('ok');
  });

  it('disables the radio when probe result is failing', () => {
    const markup = render([harness()], { claude: probeFail() });

    expect(markup).toContain('disabled=""');
  });

  it('shows failing_reason in the row text when probe fails', () => {
    const markup = render([harness()], { claude: probeFail('not logged in') });

    expect(markup).toContain('not logged in');
  });

  it('does not disable the radio when probeResults is an empty dict and enabled is false', () => {
    // probe-based path: no entry in probeResults means ok===false is false → enabled
    const markup = render([harness({ enabled: false })], {});

    expect(markup).not.toContain('disabled=""');
    // must fall back to harnessLineText, not accidentally call harnessProbeLineText(harness, undefined)
    expect(markup).not.toContain('probe failed');
  });

  it('disables the radio when probeResults is absent and enabled is false', () => {
    // fallback to harness.enabled when probeResults not passed — preserves unit-test baseline
    const markup = render([harness({ enabled: false })]);

    expect(markup).toContain('disabled=""');
  });
});
