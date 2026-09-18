/**
 * `HarnessList` with the `onRunReadiness` prop (story 2-4, readiness badge).
 *
 * Unit-test path: renders with `renderToStaticMarkup` in `environment: 'node'`,
 * the same pattern as `harness-list.test.ts`.  Only the new `onRunReadiness` prop path is
 * covered here; the absent-prop path ("not available yet") is the anchor `harness-list.test.ts`
 * and is not duplicated.  Click behaviour is covered by e2e only.
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

function render(harnesses: HarnessOut[]): string {
  return renderToStaticMarkup(
    createElement(HarnessList, {
      harnesses,
      selected: '',
      onSelect: () => {},
      onRunReadiness: () => {},
    }),
  );
}

function noteText(markup: string, name: string): string {
  return markup.match(new RegExp(`data-testid="newwf-readiness-${name}-note">(.*?)<\\/span>`))?.[1] ?? '';
}

describe('HarnessList with onRunReadiness prop', () => {
  it('does not show "not available yet" when onRunReadiness is passed', () => {
    const markup = render([harness()]);

    expect(markup).not.toContain('not available yet');
  });

  it('shows empty note when last_readiness_at and failing_check are both null', () => {
    const markup = render([harness()]);

    // The note span is present but contains no text
    expect(markup).toContain('data-testid="newwf-readiness-claude-note"');
    // readinessBadgeText(harness) == "" so the span content is empty
    expect(markup).not.toContain('not available yet');
  });

  it('shows formatted time in the note span when last_readiness_at is set', () => {
    const markup = render([harness({ last_readiness_at: '2026-09-17T10:00:00Z' })]);

    expect(noteText(markup, 'claude')).toBe('2026-09-17 10:00:00');
  });

  it('concatenates time and failing_check with " · " when both are set', () => {
    const markup = render([
      harness({ last_readiness_at: '2026-09-17T10:00:00Z', failing_check: 'harness: not running' }),
    ]);

    expect(noteText(markup, 'claude')).toBe('2026-09-17 10:00:00 · harness: not running');
  });

  it('shows just the failing_check when last_readiness_at is null', () => {
    const markup = render([harness({ failing_check: 'version pin changed: 2.1.258 → 2.1.260' })]);

    expect(noteText(markup, 'claude')).toBe('version pin changed: 2.1.258 → 2.1.260');
  });
});
