// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { DrawerPanel } from '../../src/components/run/HelperDrawer';

afterEach(cleanup);

it('renders the head slot before close, then the children in the body', () => {
  render(
    createElement(
      DrawerPanel,
      { head: createElement('span', null, 'the head'), onClose: () => {} },
      createElement('p', null, 'the body'),
    ),
  );

  const panel = screen.getByTestId('step-drawer');
  expect(panel.className).toBe('step-drawer-panel');
  const header = panel.querySelector('.step-drawer-header')!;
  expect(Array.from(header.children).map((c) => c.textContent)).toEqual(['the head', 'close']);
  expect(panel.querySelector('.step-drawer-body')!.textContent).toBe('the body');
});

it('calls onClose from the close button', () => {
  const onClose = vi.fn();
  render(createElement(DrawerPanel, { head: null, onClose }, null));
  fireEvent.click(screen.getByRole('button', { name: 'close' }));
  expect(onClose).toHaveBeenCalledTimes(1);
});

it('takes a test id and an extra class', () => {
  render(
    createElement(
      DrawerPanel,
      { head: null, onClose: () => {}, testId: 'origin-drawer', className: 'origin-drawer' },
      null,
    ),
  );
  const panel = screen.getByTestId('origin-drawer');
  expect(panel.className).toBe('step-drawer-panel origin-drawer');
});
