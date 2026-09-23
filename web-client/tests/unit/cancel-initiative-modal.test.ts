/**
 * `CancelInitiativeModal.tsx` (S8, AD-13): the initiative-wide Cancel confirm, its own
 * component beside `CancelModal.tsx` (the module doc explains why). Stateless
 * (`renderToStaticMarkup`); the click wiring is `tests/e2e/initiative-detail.spec.ts`'s own
 * subject, in a real browser.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import CancelInitiativeModal from '../../src/components/initiative/CancelInitiativeModal';

describe('CancelInitiativeModal', () => {
  it('names the slug and every real effect of cancelling', () => {
    const html = renderToStaticMarkup(
      createElement(CancelInitiativeModal, {
        slug: 'q4',
        posting: false,
        onConfirm: () => {},
        onDismiss: () => {},
      }),
    );

    expect(html).toContain('data-testid="newin-cancel-confirm"');
    expect(html).toContain('cancel initiative q4?');
    expect(html).toContain('dependents first');
  });

  it('offers exactly Cancel initiative (destructive) and Keep running', () => {
    const html = renderToStaticMarkup(
      createElement(CancelInitiativeModal, {
        slug: 'q4',
        posting: false,
        onConfirm: () => {},
        onDismiss: () => {},
      }),
    );

    expect(html).toContain('data-testid="newin-cancel-confirm-yes"');
    expect(html).toContain('Cancel initiative');
    expect(html).toContain('data-testid="newin-cancel-confirm-no"');
    expect(html).toContain('Keep running');
  });

  it('disables both actions while a signal is in flight', () => {
    const html = renderToStaticMarkup(
      createElement(CancelInitiativeModal, {
        slug: 'q4',
        posting: true,
        onConfirm: () => {},
        onDismiss: () => {},
      }),
    );

    expect(html).toContain('data-testid="newin-cancel-confirm-yes" disabled=""');
    expect(html).toContain('data-testid="newin-cancel-confirm-no" disabled=""');
  });

  it('never congratulates or apologises (NFR-8)', () => {
    const html = renderToStaticMarkup(
      createElement(CancelInitiativeModal, {
        slug: 'q4',
        posting: false,
        onConfirm: () => {},
        onDismiss: () => {},
      }),
    ).toLowerCase();

    expect(html).not.toContain('sorry');
    expect(html).not.toContain('are you sure you want to');
  });
});
