// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { components } from '../../src/api/schema';
import SpendTable from '../../src/components/metrics/SpendTable';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { $originTarget, closeOrigin } from '../../src/stores/metric-ui';
import { entry } from './metrics-fixtures';

type Spend = components['schemas']['ProjectSpendOut'];

const spend = (id: string, over: Partial<Spend> = {}): Spend => ({
  cancelled: { gateway: '0.5', harness: '0.25', runs: 1 },
  gateway: '10',
  gateway_reported: true,
  harness: '5',
  harness_reported: true,
  project_id: id,
  project_name: `P ${id}`,
  runs: 4,
  subscription: null,
  ...over,
});

beforeEach(() => {
  $catalogue.set({
    status: 'ready',
    entries: Object.fromEntries(
      ['spend.month', 'cost.harness', 'spend.month_cancelled'].map((id) => [id, entry(id)]),
    ),
  });
});
afterEach(() => {
  cleanup();
  closeOrigin();
  resetCatalogue();
});

describe('SpendTable', () => {
  it('puts the chosen project first, marked current', () => {
    render(
      createElement(SpendTable, { items: [spend('a'), spend('b'), spend('c')], projectId: 'b' }),
    );
    const rows = screen.getAllByTestId(/^metrics-spend-row-/);
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual([
      'metrics-spend-row-b',
      'metrics-spend-row-a',
      'metrics-spend-row-c',
    ]);
    expect(rows[0]!.getAttribute('data-current')).toBe('true');
    expect(rows[1]!.getAttribute('data-current')).toBeNull();
    expect(
      within(rows[0]!)
        .getAllByText(/^\$/)
        .map((e) => e.textContent),
    ).toEqual(['$10.00', '$5.00', '$0.50', '$0.25']);
  });

  it('reads not available for unreported sides', () => {
    render(
      createElement(SpendTable, {
        items: [spend('a', { harness_reported: false }), spend('b', { gateway_reported: false })],
        projectId: null,
      }),
    );
    expect(
      within(screen.getByTestId('metrics-spend-row-a')).getAllByText('not available'),
    ).toHaveLength(2);
    expect(
      within(screen.getByTestId('metrics-spend-row-b')).getAllByText('not available'),
    ).toHaveLength(2);
  });

  it('prints the list-price words once, only with a subscription', () => {
    render(
      createElement(SpendTable, {
        items: [spend('a', { subscription: true }), spend('b', { subscription: true })],
        projectId: null,
      }),
    );
    expect(screen.getAllByTestId('metrics-spend-list-price')).toHaveLength(1);
    cleanup();
    for (const subscription of [false, null]) {
      render(createElement(SpendTable, { items: [spend('a', { subscription })], projectId: null }));
      expect(screen.queryByTestId('metrics-spend-list-price')).toBeNull();
      cleanup();
    }
  });

  it('opens the origin drawer target on a money cell', () => {
    render(createElement(SpendTable, { items: [spend('a')], projectId: null }));
    fireEvent.click(within(screen.getByTestId('metrics-spend-row-a')).getByText('$10.00'));
    expect($originTarget.get()?.value).toMatchObject({
      metric_id: 'spend.month',
      scope_type: 'project',
      value_num: '10',
    });
  });
});
