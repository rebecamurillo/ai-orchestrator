/**
 * `ConfirmAction.tsx` (6.4, FR-20) — the inline confirm, reusable by 6.5's *Skip epic*.
 *
 * `vitest.config.ts` runs in `environment: 'node'` with no DOM-mounting library, so what is
 * asserted here is the closed render: the single trigger button, its test id, its label, and
 * the fact that the confirm line is *not* on the screen until it is opened. Opening it,
 * confirming and keeping are `tests/e2e/run-detail-skip-story.spec.ts`'s job, in a real
 * browser — the same split `run-artifacts.test.ts` draws for `ArtifactsPanel`.
 *
 * The closed render is the load-bearing half for this codebase: it is what every existing
 * `run-stop-body-*.test.ts` sees, and it had to stay byte-compatible with the plain button
 * those specs were written against.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import ConfirmAction from '../../src/components/run/ConfirmAction';

function render(over: Partial<Parameters<typeof ConfirmAction>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(ConfirmAction, {
      kind: 'skip_story',
      label: 'Skip story',
      line: 'skip story 2: …',
      confirmLabel: 'Skip story',
      keepLabel: 'Keep',
      disabled: false,
      onConfirm: () => {},
      ...over,
    }),
  );
}

describe('ConfirmAction', () => {
  it('renders one plain signal button until it is opened', () => {
    const html = render();

    expect(html).toContain('data-testid="wf-signal-skip_story"');
    expect(html).toContain('Skip story');
    expect(html).not.toContain('data-testid="wf-confirm-skip_story"');
    expect(html).not.toContain('Keep');
  });

  it('disables the trigger while a signal is in flight', () => {
    expect(render({ disabled: true })).toContain('disabled=""');
    expect(render({ disabled: false })).not.toContain('disabled=""');
  });

  it('is keyed on the signal kind alone, so 6.5 reuses it unchanged', () => {
    const html = render({ kind: 'skip_epic', label: 'Skip epic' });

    expect(html).toContain('data-testid="wf-signal-skip_epic"');
    expect(html).toContain('Skip epic');
  });

  it('never injects markup', () => {
    const html = render({ label: '<script>x</script>' });

    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
  });
});
