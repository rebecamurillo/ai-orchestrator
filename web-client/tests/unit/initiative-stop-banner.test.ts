// @vitest-environment jsdom
/** Story 11.5: the stop banner (AC1–AC6, AC9). */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { POST, GET, PUT } = vi.hoisted(() => ({ POST: vi.fn(), GET: vi.fn(), PUT: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { POST, GET, PUT } }));

import StopBanner from '../../src/components/initiative/StopBanner';
import { $poll } from '../../src/stores/poll';
import { turn } from './conversation-fixtures';
import { detail, step, workflow, type Detail, type Step } from './initiative-fixtures';

const session = { workflow: 'spec', step: 'ux', kind: 'session', state: 'open', id: 's1' };

function make(stepOver: Partial<Step>, over: Partial<Detail> = {}, wfOver = {}): Detail {
  return detail({
    status: 'waiting for her',
    attention: 'blocked',
    reason: '',
    sessions: [],
    workflows: [
      workflow('spec', 1, { run_id: 'run-s', steps: [step('ux', stepOver)], ...wfOver }),
      workflow('build', 2, { type: 'auto' }),
    ],
    ...over,
  } as Partial<Detail>);
}

function mount(d: Detail, selected = 1, reopen?: string) {
  const onCancel = vi.fn();
  render(
    createElement(StopBanner, {
      detail: d,
      selectedPosition: selected,
      onCancel,
      reopen: reopen ? createElement('button', { 'data-testid': 'slot' }, reopen) : undefined,
    }),
  );
  return onCancel;
}

const stalled = (over: Partial<Detail> = {}) =>
  make(
    {
      run_id: 'run-s',
      turns: [turn(1), turn(2, { status: 'failed', failure_reason: 'stalled: no activity' })],
    } as Partial<Step>,
    { sessions: [session], ...over } as Partial<Detail>,
  );

beforeEach(() => {
  POST.mockReset();
  GET.mockReset();
  PUT.mockReset();
});
afterEach(cleanup);

describe('StopBanner', () => {
  it('AC1: merge conflict is amber, states the files and cancels', () => {
    const onCancel = mount(
      make({ kind: 'automatic', park_kind: 'merge_conflict', conflict_files: ['a.md'] }),
    );
    const banner = screen.getByTestId('ini-stop');
    expect(banner.getAttribute('data-signal')).toBe('needs-you');
    expect(banner.textContent).toContain('merge conflict · a.md');
    expect(banner.textContent).toContain('resolve 1 file(s)');
    fireEvent.click(screen.getByTestId('ini-cancel'));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('ini-restart')).toBeNull();
  });

  it('AC2: Restart step posts the session retry once, refreshes, and is disabled in flight', async () => {
    let done: (v: unknown) => void = () => {};
    POST.mockReturnValue(new Promise((r) => (done = r)));
    mount(stalled());
    expect(screen.getByTestId('ini-stop').getAttribute('data-signal')).toBe('failed');
    const tick = $poll.get();
    const restart = screen.getByTestId('ini-restart') as HTMLButtonElement;
    expect(restart.textContent).toBe('Restart step');
    fireEvent.click(restart);
    fireEvent.click(restart);
    expect(restart.disabled).toBe(true);
    done({ data: {} });
    await waitFor(() => expect($poll.get()).toBe(tick + 1));
    expect(POST).toHaveBeenCalledTimes(1);
    expect(POST).toHaveBeenCalledWith('/runs/{run_id}/session/retry', {
      params: { path: { run_id: 'run-s' } },
    });
  });

  it('AC2: a refused restart renders its detail and does not refresh', async () => {
    POST.mockResolvedValue({ error: { detail: 'session closed' } });
    mount(stalled());
    const tick = $poll.get();
    fireEvent.click(screen.getByTestId('ini-restart'));
    expect((await screen.findByRole('alert')).textContent).toBe('session closed');
    expect($poll.get()).toBe(tick);
  });

  it('AC2: a thrown restart is reported', async () => {
    POST.mockRejectedValue(new Error('down'));
    mount(stalled());
    fireEvent.click(screen.getByTestId('ini-restart'));
    expect((await screen.findByRole('alert')).textContent).toBe('The step was not restarted.');
  });

  it('AC3: a failed spec Run reopens the conversation step with the head as reason', async () => {
    POST.mockResolvedValue({ data: {} });
    mount(
      make(
        { turns: [turn(1)] } as Partial<Step>,
        { status: 'failed', reason: 'Run cancelled' } as Partial<Detail>,
        { status: 'failed' },
      ),
    );
    fireEvent.click(screen.getByTestId('ini-restart'));
    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
    expect(POST).toHaveBeenCalledWith('/initiatives/{initiative_id}/reopen', {
      params: { path: { initiative_id: 'ini-1' } },
      body: { step: 'ux', reason: 'Run cancelled' },
    });
  });

  it('AC3: a failed turn without an open session shows no Restart step', () => {
    mount(stalled({ sessions: [] }));
    expect(screen.getByTestId('ini-stop')).toBeTruthy();
    expect(screen.queryByTestId('ini-restart')).toBeNull();
  });

  it('AC4: a failed automatic step is red with no body and no restart', () => {
    mount(
      make({ kind: 'automatic' }, { status: 'failed' } as Partial<Detail>, { status: 'failed' }),
    );
    expect(screen.getByText('failed')).toBeTruthy();
    expect(document.querySelector('.ini-stop-body')).toBeNull();
    expect(screen.queryByTestId('ini-restart')).toBeNull();
    expect(screen.getAllByTestId('ini-cancel')).toHaveLength(1);
  });

  it('AC5: advance blocked shows the reason, the reopen slot and no ini-reopen', () => {
    mount(make({}, { reason: 'preflight: harness: not ready' }), 2, 'slot content');
    expect(screen.getByTestId('ini-stop').textContent).toContain('preflight: harness: not ready');
    expect(screen.getByTestId('slot').textContent).toBe('slot content');
    expect(screen.queryByTestId('ini-reopen')).toBeNull();
  });

  it('AC5: the slot renders only in the advance banner', () => {
    mount(stalled(), 1, 'slot content');
    expect(screen.queryByTestId('slot')).toBeNull();
  });

  it('AC6: the budget banner holds the empty field for the not-started workflow', () => {
    mount(
      make({ status: 'done' }, {
        reason: 'no project budget',
        project_name: 'familio',
      } as Partial<Detail>),
      2,
    );
    expect(screen.getByTestId('ini-stop').textContent).toContain(
      'build not started: project familio has no default budget',
    );
    expect((screen.getByTestId('ini-budget') as HTMLInputElement).value).toBe('');
    expect((screen.getByTestId('ini-budget-set') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByTestId('ini-cancel')).toHaveLength(1);
  });

  it('AC9: no banner when cancelled, done or running', () => {
    for (const over of [
      { status: 'cancelled', reason: 'x' },
      { status: 'done', reason: 'x' },
      { status: 'running', attention: 'your_turn', reason: '' },
    ]) {
      mount(make({}, over as Partial<Detail>));
      expect(screen.queryByTestId('ini-stop')).toBeNull();
      cleanup();
    }
  });
});

describe('StopBanner restart after the answer (review, 2026-11-26)', () => {
  it('stays disabled after an accepted restart, re-enables after a refusal', async () => {
    POST.mockResolvedValueOnce({ data: {} });
    mount(stalled());
    const restart = screen.getByTestId('ini-restart') as HTMLButtonElement;
    const tick = $poll.get();
    fireEvent.click(restart);
    await waitFor(() => expect($poll.get()).toBe(tick + 1));
    expect(restart.disabled).toBe(true);
    fireEvent.click(restart);
    expect(POST).toHaveBeenCalledTimes(1);
    cleanup();
    POST.mockResolvedValueOnce({ error: { detail: 'session closed' } });
    mount(stalled());
    fireEvent.click(screen.getByTestId('ini-restart'));
    await screen.findByRole('alert');
    expect((screen.getByTestId('ini-restart') as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('StopBanner with a parked Run (operator resolution 2026-11-26, story 11.6)', () => {
  it('renders no ini-stop for a build Run needs_you, with either selection', () => {
    const d = make({}, {
      reason: 'verify failed: make test exited 2',
      runs: [{ id: 'run-b', status: 'needs_you', created_at: '2026-11-22T10:00:00Z' }],
    } as Partial<Detail>);
    mount(d, 1, 'slot content');
    expect(screen.queryByTestId('ini-stop')).toBeNull();
    cleanup();
    mount(d, 2, 'slot content');
    expect(screen.queryByTestId('ini-stop')).toBeNull();
  });
});
