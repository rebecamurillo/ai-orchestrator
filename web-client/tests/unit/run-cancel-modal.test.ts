/**
 * `CancelModal.tsx` (4.15, FR-20): the one modal in the product, and its confirm text states
 * what cancelling actually does, in mechanism (NFR-8). Stateless (`renderToStaticMarkup`);
 * the click wiring is `tests/e2e/run-detail.spec.ts`'s own subject, in a real browser.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import CancelModal from '../../src/components/run/CancelModal';

describe('CancelModal', () => {
  it('names the branch and every real effect of cancelling', () => {
    const html = renderToStaticMarkup(
      createElement(CancelModal, {
        branch: 'epics/1',
        posting: false,
        onConfirm: () => {},
        onDismiss: () => {},
      }),
    );

    expect(html).toContain('data-testid="wf-cancel-confirm"');
    expect(html).toContain('cancel run epics/1?');
    expect(html).toContain('running processes are killed');
    expect(html).toContain('worktrees removed');
    expect(html).toContain('branches created by this run and never pushed are deleted');
  });

  it('offers exactly Cancel run (destructive) and Keep running', () => {
    const html = renderToStaticMarkup(
      createElement(CancelModal, {
        branch: 'epics/1',
        posting: false,
        onConfirm: () => {},
        onDismiss: () => {},
      }),
    );

    expect(html).toContain('data-testid="wf-cancel-confirm-yes"');
    expect(html).toContain('Cancel run');
    expect(html).toContain('data-testid="wf-cancel-confirm-no"');
    expect(html).toContain('Keep running');
  });

  it('never congratulates or apologises (NFR-8)', () => {
    const html = renderToStaticMarkup(
      createElement(CancelModal, {
        branch: 'epics/1',
        posting: false,
        onConfirm: () => {},
        onDismiss: () => {},
      }),
    ).toLowerCase();

    expect(html).not.toContain('sorry');
    expect(html).not.toContain('are you sure you want to');
  });
});
