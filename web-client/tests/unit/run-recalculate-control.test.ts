// @vitest-environment jsdom
/** `RecalculateControl` (epic 3 story 3, AC4 and AC5). */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import RecalculateControl from '../../src/components/run/RecalculateControl';
import { version } from './metrics-fixtures';

afterEach(cleanup);

function calc(over = {}) {
  return {
    ended_at: null,
    entry_point: ['manual'],
    id: 'c',
    output: '',
    queued_at: '2026-11-19T14:02:05Z',
    run_id: 'r',
    started_at: '2026-11-19T14:02:11Z',
    state: 'running',
    target_n: 4,
    ...over,
  };
}

function mount(over: Record<string, unknown> = {}) {
  const onConfirm = vi.fn();
  const view = render(
    createElement(RecalculateControl, {
      status: 'done',
      versions: [version(1), version(2), version(3)],
      calc: null,
      calcError: null,
      onConfirm,
      ...over,
    } as never),
  );
  return { onConfirm, ...view };
}

describe('RecalculateControl', () => {
  it.each(['queued', 'running', 'needs_you'])('renders nothing for a %s Run', (status) => {
    const { container } = mount({ status });
    expect(container.innerHTML).toBe('');
  });

  it.each(['done', 'failed', 'cancelled'])('offers the button for a %s Run', (status) => {
    mount({ status });
    expect(screen.getByRole('button', { name: 'RECALCULATE METRICS' })).toBeTruthy();
  });

  it('confirms with the versions-derived line and posts once', () => {
    const { onConfirm } = mount();
    fireEvent.click(screen.getByRole('button', { name: 'RECALCULATE METRICS' }));
    expect(screen.getByTestId('wf-confirm-recalculate-line').textContent).toBe(
      "Creates v4 of this Run's metrics: part A from the Run record. v1 to v3 are kept.",
    );
    fireEvent.click(screen.getByTestId('wf-confirm-recalculate-yes'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('Keep closes the confirm and posts nothing', () => {
    const { onConfirm } = mount();
    fireEvent.click(screen.getByRole('button', { name: 'RECALCULATE METRICS' }));
    fireEvent.click(screen.getByTestId('wf-confirm-recalculate-keep'));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'RECALCULATE METRICS' })).toBeTruthy();
  });

  it.each(['queued', 'running'])(
    'replaces the button with the calculating line while %s',
    (state) => {
      mount({ calc: calc({ state }) });
      expect(screen.getByTestId('wf-calc-line').textContent).toBe(
        'calculating v4 · started 14:02:11',
      );
      expect(screen.queryByRole('button', { name: 'RECALCULATE METRICS' })).toBeNull();
    },
  );

  it('shows the failure line and the output in a command block, with the button again', () => {
    mount({ calc: calc({ state: 'failed', output: 'boom' }) });
    expect(screen.getByTestId('wf-calc-line').textContent).toBe(
      'calculation v4 failed · no version created ·',
    );
    expect(screen.getByTestId('wf-calc-output').textContent).toBe('boom');
    expect(screen.getByRole('button', { name: 'RECALCULATE METRICS' })).toBeTruthy();
  });

  it('shows a refused start', () => {
    mount({
      calcError: { status: 409, title: 'busy', type: 'x', detail: 'a calculation is running' },
    });
    expect(screen.getByText('a calculation is running')).toBeTruthy();
    mount({ calcError: { status: 500, title: 'broken', type: 'x' } });
    expect(screen.getByText('broken')).toBeTruthy();
  });
});
