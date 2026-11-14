// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import VersionSelector from '../../src/components/metrics/VersionSelector';
import { version } from './metrics-fixtures';

afterEach(cleanup);

const many = (n: number) => Array.from({ length: n }, (_, i) => version(i + 1));
const segments = () =>
  Array.from(document.querySelectorAll('.metric-version-segment')).map((b) => b.textContent);

it('renders nothing for an empty list', () => {
  const { container } = render(
    createElement(VersionSelector, { versions: [], selected: 1, onSelect: () => {} }),
  );
  expect(container.innerHTML).toBe('');
});

it('shows v1 · v2 · v3 latest with no select, and the detail line', () => {
  const onSelect = vi.fn();
  render(
    createElement(VersionSelector, {
      versions: [version(1), version(2), version(3, { methods_changed: ['cost.total'] })],
      selected: 3,
      onSelect,
    }),
  );
  expect(segments()).toEqual(['v1', 'v2', 'v3 latest']);
  expect(screen.queryByRole('combobox')).toBeNull();
  expect(document.querySelector('.metric-version-detail')!.textContent).toBe(
    'calculated 2026-11-19 14:02Z · at attempt end + workflow step · methods changed: cost.total',
  );
  expect(screen.getByRole('button', { name: 'v3 latest' }).getAttribute('aria-pressed')).toBe(
    'true',
  );
  fireEvent.click(screen.getByRole('button', { name: 'v1' }));
  expect(onSelect).toHaveBeenCalledWith(1);
});

it('shows four segments and a select of all seven when there are seven versions', () => {
  const onSelect = vi.fn();
  render(createElement(VersionSelector, { versions: many(7), selected: 7, onSelect }));
  expect(segments()).toEqual(['v4', 'v5', 'v6', 'v7 latest']);
  const select = screen.getByRole('combobox', { name: 'result version' });
  expect(Array.from(select.querySelectorAll('option')).map((o) => o.textContent)).toEqual([
    'v1',
    'v2',
    'v3',
    'v4',
    'v5',
    'v6',
    'v7 latest',
  ]);
  fireEvent.change(select, { target: { value: '2' } });
  expect(onSelect).toHaveBeenCalledWith(2);
});

it('omits the detail line when the selected version is not in the list', () => {
  render(createElement(VersionSelector, { versions: many(2), selected: 9, onSelect: () => {} }));
  expect(document.querySelector('.metric-version-detail')).toBeNull();
});
