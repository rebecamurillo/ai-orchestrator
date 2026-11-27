// @vitest-environment jsdom
/** Story 11.5: the gate's defects block (AC7). */
import { createElement } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import DefectsBlock from '../../src/components/initiative/DefectsBlock';
import { convStep, turn } from './conversation-fixtures';

afterEach(cleanup);

const gate = (over = {}) =>
  turn(1, {
    author: 'gate',
    defects: 2,
    owner: 'tech',
    started_at: '2026-11-22T22:10:00Z',
    message: '1. one\n2. two',
    ...over,
  });

describe('DefectsBlock', () => {
  it('renders the attribution, the eyebrow and the message verbatim', () => {
    render(
      createElement(DefectsBlock, {
        turn: gate(),
        step: convStep({ id: 'tech' }),
        gateAgent: 'delivery-lead',
      }),
    );
    expect(screen.getByText('Gate · delivery-lead · 22:10')).toBeTruthy();
    expect(screen.getByText('2 DEFECTS · OWNER TECH')).toBeTruthy();
    expect(document.querySelector('.ini-defects-text')?.textContent).toBe('1. one\n2. two');
  });

  it('renders a message with markup as text', () => {
    render(
      createElement(DefectsBlock, {
        turn: gate({ message: 'a <b>bold</b> claim' }),
        step: convStep({ id: 'tech' }),
        gateAgent: null,
      }),
    );
    expect(document.querySelector('.ini-defects-text b')).toBeNull();
    expect(document.querySelector('.ini-defects-text')?.textContent).toBe('a <b>bold</b> claim');
    expect(screen.getByText('Gate · 22:10')).toBeTruthy();
  });
});
