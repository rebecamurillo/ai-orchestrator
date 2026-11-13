// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import ConfirmAction from '../../src/components/run/ConfirmAction';
import RecalculateControl from '../../src/components/run/RecalculateControl';
import { recalcRequested } from '../../src/lib/run/metrics-glance';

afterEach(cleanup);

const control = (opened?: boolean) =>
  createElement(RecalculateControl, {
    status: 'done',
    versions: [],
    calc: null,
    calcError: null,
    onConfirm: () => {},
    opened,
  });

describe('RecalculateControl opened (story 4.3, AC9)', () => {
  it('opens the confirm on first render when asked', () => {
    render(control(true));
    expect(screen.getByTestId('wf-confirm-recalculate')).toBeTruthy();
  });

  it('keeps the closed button otherwise', () => {
    render(control());
    expect(screen.getByTestId('wf-signal-recalculate')).toBeTruthy();
    expect(screen.queryByTestId('wf-confirm-recalculate')).toBeNull();
  });
});

describe('recalcRequested', () => {
  it('is true only for recalculate=1', () => {
    expect(recalcRequested('?tab=metrics&recalculate=1')).toBe(true);
    expect(recalcRequested('?recalculate=0')).toBe(false);
    expect(recalcRequested('')).toBe(false);
  });
});

describe('ConfirmAction initialOpen', () => {
  it('starts open and keep closes it', () => {
    render(
      createElement(ConfirmAction, {
        kind: 'x',
        label: 'L',
        line: 'line',
        confirmLabel: 'go',
        keepLabel: 'keep',
        disabled: false,
        onConfirm: () => {},
        initialOpen: true,
      }),
    );
    fireEvent.click(screen.getByTestId('wf-confirm-x-keep'));
    expect(screen.getByTestId('wf-signal-x')).toBeTruthy();
  });
});
