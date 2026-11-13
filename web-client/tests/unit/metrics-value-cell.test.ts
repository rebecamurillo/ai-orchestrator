// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, expect, it } from 'vitest';

import OriginDrawer from '../../src/components/metrics/OriginDrawer';
import ValueCell from '../../src/components/metrics/ValueCell';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { $originTarget, closeOrigin } from '../../src/stores/metric-ui';
import { entry, target, value } from './metrics-fixtures';

beforeEach(() => {
  $catalogue.set({
    status: 'ready',
    entries: { 'cost.total': entry('cost.total'), 'cost.gateway': entry('cost.gateway') },
  });
});

afterEach(() => {
  cleanup();
  closeOrigin();
  resetCatalogue();
});

const html = (t: ReturnType<typeof target>) =>
  renderToStaticMarkup(createElement(ValueCell, { target: t }));

it('renders nothing for a metric with no catalogue entry', () => {
  const markup = html(target({ value: value({ metric_id: 'ghost' }) }));
  expect(markup).toBe('');
});

it('reads the missing word and never a zero figure', () => {
  const markup = html(target({ value: value({ value_num: null, missing: 'not recorded' }) }));
  expect(markup).toContain('<span class="metric-missing">not recorded</span>');
  expect(markup).not.toContain('$0.00');
  expect(markup).not.toContain('—');
  expect(markup).not.toMatch(/>0</);
});

it('follows a carried value with from v{n} and shows the formatted figure', () => {
  const markup = html(target({ value: value({ carried_from: 2 }) }));
  expect(markup).toContain('$15.35');
  expect(markup).toContain('from v2');
});

it('opens the origin drawer on click and on Enter for exactly that value', () => {
  const first = target();
  render(
    createElement(
      'div',
      null,
      createElement(ValueCell, { target: first }),
      createElement(OriginDrawer),
    ),
  );
  const cell = screen.getByRole('button', { name: /Run 7 label of cost.total \$15.35/ });

  fireEvent.click(cell);
  expect($originTarget.get()).toBe(first);
  expect(screen.getByTestId('origin-drawer')).toBeTruthy();

  closeOrigin();
  fireEvent.keyDown(cell, { key: 'Enter' });
  fireEvent.click(cell);
  expect($originTarget.get()).toBe(first);
});

it('swaps the open drawer to the next value and closes on Escape or close', () => {
  const a = target({ runLabel: 'Run A' });
  const b = target({ runLabel: 'Run B', value: value({ value_num: '2' }) });
  render(
    createElement(
      'div',
      null,
      createElement(ValueCell, { target: a }),
      createElement(ValueCell, { target: b }),
      createElement(OriginDrawer),
    ),
  );
  fireEvent.click(screen.getByRole('button', { name: /^Run A/ }));
  expect(screen.getByText(/Run A · /)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /^Run B/ }));
  expect($originTarget.get()).toBe(b);
  expect(screen.getByText(/Run B · /)).toBeTruthy();
  expect(screen.getAllByTestId('origin-drawer')).toHaveLength(1);

  fireEvent.keyDown(document, { key: 'Escape' });
  expect(screen.queryByTestId('origin-drawer')).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: /^Run B/ }));
  fireEvent.click(screen.getByRole('button', { name: 'close' }));
  expect(screen.queryByTestId('origin-drawer')).toBeNull();
});
