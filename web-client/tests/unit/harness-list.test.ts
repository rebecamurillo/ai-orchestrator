/**
 * `HarnessList.tsx` (4.13) holds no state and runs no effect, so it renders outright with
 * `renderToStaticMarkup` in `environment: 'node'` — the `Diagram.tsx` precedent.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import HarnessList from '../../src/components/HarnessList';
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

function render(harnesses: HarnessOut[], selected = ''): string {
  return renderToStaticMarkup(
    createElement(HarnessList, { harnesses, selected, onSelect: () => {} }),
  );
}

describe('HarnessList', () => {
  it('renders the disabled line verbatim, under the harness test id', () => {
    const markup = render([harness()]);

    expect(markup).toContain('data-testid="newwf-harness-claude"');
    expect(markup).toContain('claude · disabled: no readiness run · last readiness — ·');
  });

  it('offers the re-run readiness control on every harness, disabled or not', () => {
    const markup = render([harness()]);

    expect(markup).toContain('data-testid="newwf-readiness-claude"');
    expect(markup).toContain('re-run readiness');
  });

  it('disables the radio of a harness that is not enabled', () => {
    expect(render([harness()])).toContain('disabled=""');
  });

  it('leaves an enabled harness selectable', () => {
    expect(render([harness({ enabled: true })])).not.toContain('disabled=""');
  });

  it('names the group with a legend, so the radios are not an unnamed set', () => {
    const markup = render([harness()]);

    expect(markup).toContain('<fieldset');
    expect(markup).toContain('<legend');
    expect(markup).toContain('HARNESS');
  });

  it('points the link at the readiness endpoint and states that it is not served yet', () => {
    const markup = render([harness()]);

    expect(markup).toContain('href="/api/harnesses/claude/readiness"');
    expect(markup).toContain('data-testid="newwf-readiness-claude-note"');
    expect(markup).toContain('not available yet');
  });
});
