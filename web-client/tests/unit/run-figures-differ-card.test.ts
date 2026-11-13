// @vitest-environment jsdom
/** `FiguresDifferCard` (epic 3 story 3, AC3): the card under the cost block. */
import { createElement } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it } from 'vitest';

import FiguresDifferCard from '../../src/components/run/FiguresDifferCard';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { entry } from './metrics-fixtures';

const LINE = 'gateway $15.35 · harness $16.01 · harness is $0.66 higher (4.3 %)';
const GATE = 'the budget gate uses the higher figure';

beforeEach(() => {
  $catalogue.set({ status: 'ready', entries: { 'cost.figure_gap': entry('cost.figure_gap') } });
});
afterEach(() => {
  cleanup();
  resetCatalogue();
});

it('reads eyebrow, line, gate and the catalogue reason, with a hint control', () => {
  const { container } = render(
    createElement(FiguresDifferCard, { line: LINE, gate: GATE, reason: 'the reason text' }),
  );
  const card = screen.getByTestId('wf-figures-differ');
  expect(card.getAttribute('role')).toBe('note');
  expect(card.textContent).toContain('FIGURES DIFFER');
  expect(card.textContent).toContain(LINE);
  expect(card.textContent).toContain(`${GATE} · the reason text`);
  expect(container.querySelector('button.metric-hint-control')).not.toBeNull();
});

it('renders without a reason when the catalogue has none', () => {
  render(createElement(FiguresDifferCard, { line: LINE, gate: GATE, reason: null }));
  const text = screen.getByTestId('wf-figures-differ').textContent!;
  expect(text).toContain(GATE);
  expect(text).not.toContain(`${GATE} ·`);
});
