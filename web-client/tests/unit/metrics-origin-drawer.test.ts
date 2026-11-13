// @vitest-environment jsdom
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import OriginDrawer from '../../src/components/metrics/OriginDrawer';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import {
  $openHint,
  $originTarget,
  closeHint,
  closeOrigin,
  openOrigin,
} from '../../src/stores/metric-ui';
import { RUN_ID, entry, target, value } from './metrics-fixtures';

beforeEach(() => {
  $catalogue.set({ status: 'ready', entries: { 'cost.total': entry('cost.total') } });
});

afterEach(() => {
  cleanup();
  closeOrigin();
  closeHint();
  resetCatalogue();
  vi.unstubAllGlobals();
});

const KEYS = [
  'metric',
  'method',
  'calculated',
  'entry point',
  'result version',
  'project',
  'Run',
  'template',
  'harness',
  'model',
  'repository',
  'branch',
  'commit',
  'base commit',
];

function open(t = target()) {
  render(createElement(OriginDrawer));
  act(() => openOrigin(t));
}

it('renders nothing while closed or without a catalogue entry', () => {
  render(createElement(OriginDrawer));
  expect(screen.queryByTestId('origin-drawer')).toBeNull();
  act(() => openOrigin(target({ value: value({ metric_id: 'ghost' }) })));
  expect(screen.queryByTestId('origin-drawer')).toBeNull();
});

it('lists the fourteen keys in order, none empty, with n/a and its reason', () => {
  open();
  const rows = Array.from(document.querySelectorAll('.origin-drawer-rows tr'));
  expect(rows.map((r) => r.querySelector('th')!.textContent)).toEqual(KEYS);
  expect(
    rows.every((r) => r.querySelector('td')!.textContent!.replace('copy', '').trim() !== ''),
  ).toBe(true);
  expect(screen.getByText('n/a — a Run total spans 2 models')).toBeTruthy();
});

it('shows the value, label, state words and the Run label beside its id in the head', () => {
  open(target({ subscription: true, value: value({ carried_from: 1 }) }));
  const head = document.querySelector('.origin-drawer-head')!;
  expect(head.textContent).toContain('$15.35');
  expect(head.textContent).toContain('label of cost.total');
  expect(head.textContent).toContain('list-price equivalent · from v1');
  expect(head.textContent).toContain(`Run 7 · ${RUN_ID}`);
});

it('shows the missing word in the head instead of a figure', () => {
  open(target({ value: value({ value_num: null, missing: 'not recorded' }) }));
  expect(document.querySelector('.origin-drawer-head .metric-missing')!.textContent).toBe(
    'not recorded',
  );
});

it('copies ids, commits and branches through the clipboard', () => {
  const writeText = vi.fn();
  vi.stubGlobal('navigator', { clipboard: { writeText } });
  open();
  fireEvent.click(screen.getByRole('button', { name: 'copy branch' }));
  fireEvent.click(screen.getByRole('button', { name: 'copy Run' }));
  expect(writeText).toHaveBeenNthCalledWith(1, 'feat/x');
  expect(writeText).toHaveBeenNthCalledWith(2, RUN_ID);
  expect(screen.queryByRole('button', { name: 'copy model' })).toBeNull();
});

it('does not throw when there is no clipboard', () => {
  vi.stubGlobal('navigator', {});
  open();
  fireEvent.click(screen.getByRole('button', { name: 'copy commit' }));
});

it('shows the scope of an aggregated value and a working breakdown button', () => {
  const onBreakdown = vi.fn();
  open(target({ aggregate: { n: 4, noun: 'attempts' }, onBreakdown }));
  expect(screen.getByText(/sum of 4 attempts/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'see the breakdown' }));
  expect(onBreakdown).toHaveBeenCalledTimes(1);
});

it('shows the aggregate scope without a breakdown button when none is given', () => {
  open(target({ aggregate: { n: 2, noun: 'attempts' } }));
  expect(screen.queryByRole('button', { name: 'see the breakdown' })).toBeNull();
});

it('Escape closes the open hint first, then the drawer', () => {
  open();
  fireEvent.click(screen.getByRole('button', { name: 'how label of cost.total is calculated' }));
  expect($openHint.get()).not.toBeNull();

  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
  expect($openHint.get()).toBeNull();
  expect($originTarget.get()).not.toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'how label of cost.total is calculated' }));
  fireEvent.keyDown(document, { key: 'Escape' });
  expect($openHint.get()).toBeNull();
  expect($originTarget.get()).not.toBeNull();

  fireEvent.keyDown(document, { key: 'x' });
  expect($originTarget.get()).not.toBeNull();
  fireEvent.keyDown(document, { key: 'Escape' });
  expect($originTarget.get()).toBeNull();
});
