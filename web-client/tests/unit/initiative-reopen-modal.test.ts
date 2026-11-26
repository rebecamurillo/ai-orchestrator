// @vitest-environment jsdom
/** Story 11.6: the reopen-a-spec-step confirmation (AC2–AC4, the AC6 modal lines). */
import { createElement as h, useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { POST } = vi.hoisted(() => ({ POST: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { POST } }));

import ReopenStepModal from '../../src/components/initiative/ReopenStepModal';
import type { ReopenOrigin } from '../../src/lib/initiative/reopen';
import { $poll } from '../../src/stores/poll';
import { detail, step, workflow, type Detail, type Step } from './initiative-fixtures';

const RUN_B = '0193e5f6-0000-7000-8000-00000000bb02';
const agents = ['intake-router', 'product-lead', 'ux-lead', 'tech-lead'];

function make(over: Partial<Detail> = {}): Detail {
  const steps = ['intake', 'product', 'ux', 'tech'].map((id, i) =>
    step(id, { number: `1.${i + 1}`, agent: agents[i] } as Partial<Step>),
  );
  return detail({
    status: 'waiting for her',
    reason: 'verify failed: make test exited 2',
    current_position: 2,
    round: 1,
    runs: [{ id: RUN_B, status: 'needs_you', created_at: '2026-11-22T10:00:00Z' }],
    workflows: [
      workflow('spec', 1, { steps }),
      workflow('build', 2, { type: 'auto', run_id: RUN_B }),
    ],
    ...over,
  } as unknown as Partial<Detail>);
}

function Host(p: {
  d: Detail;
  origin?: ReopenOrigin;
  runId?: string | null;
  done?: (s: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return h(
    'div',
    null,
    h('button', { 'data-testid': 'ini-reopen', onClick: () => setOpen(true) }, 'Reopen step …'),
    open
      ? h(ReopenStepModal, {
          detail: p.d,
          origin: p.origin ?? 'build',
          runId: p.runId === undefined ? RUN_B : p.runId,
          onClose: () => setOpen(false),
          onReopened: (s: string) => {
            p.done?.(s);
            setOpen(false);
          },
        })
      : null,
  );
}

function open(props: Parameters<typeof Host>[0]) {
  render(h(Host, props));
  const opener = screen.getByTestId('ini-reopen');
  opener.focus();
  fireEvent.click(opener);
  return opener;
}

const confirm = () => screen.getByTestId('ini-reopen-confirm') as HTMLButtonElement;
const text = () => document.querySelector('[role="dialog"]')?.textContent ?? '';

beforeEach(() => POST.mockReset());
afterEach(cleanup);

describe('ReopenStepModal', () => {
  it('AC2: head, question, four unchecked radios, first turn, mechanism, disabled primary', () => {
    open({ d: make() });
    expect(screen.getByRole('dialog', { name: 'REOPEN A SPEC STEP' })).toBeTruthy();
    expect(text()).toContain('Which spec step does this build stop come from?');
    const radios = screen.getAllByRole('radio') as HTMLInputElement[];
    expect(radios).toHaveLength(4);
    expect(radios.every((r) => !r.checked)).toBe(true);
    expect(screen.getByLabelText('1.1 intake · intake-router')).toBeTruthy();
    expect(screen.getByLabelText('1.4 tech · tech-lead')).toBeTruthy();
    expect(text()).toContain('first turn: "build stopped: verify failed: make test exited 2"');
    expect(text()).toContain(
      'Run 0193…bb02 is cancelled and keeps its page. The step you choose reopens as round 2 with this stop as its first turn, on spec/familio-dessin-v2, created from main if it was deleted after the merge. Then the gate, the merge and the build run again.',
    );
    expect(confirm().textContent).toBe('Reopen step');
    expect(confirm().disabled).toBe(true);
    expect(document.activeElement).toBe(screen.getByText('Keep the build stopped'));
    fireEvent.click(confirm());
    expect(POST).not.toHaveBeenCalled();
  });

  it('AC2: an empty reason names the Run; choosing tech updates label and mechanism', () => {
    open({ d: make({ reason: '' }) });
    expect(text()).toContain('first turn: "build stopped: Run 0193…bb02 failed"');
    fireEvent.click(screen.getByLabelText('1.4 tech · tech-lead'));
    expect(confirm().textContent).toBe('Reopen tech');
    expect(confirm().disabled).toBe(false);
    expect(text()).toContain('tech reopens as round 2');
  });

  it('AC3: posts {step, reason} once, then onReopened and a tick', async () => {
    POST.mockResolvedValue({ response: { status: 200 } });
    const done = vi.fn();
    open({ d: make(), done });
    const before = $poll.get();
    fireEvent.click(screen.getByLabelText('1.4 tech · tech-lead'));
    fireEvent.click(confirm());
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(POST).toHaveBeenCalledTimes(1);
    expect(POST).toHaveBeenCalledWith('/initiatives/{initiative_id}/reopen', {
      params: { path: { initiative_id: 'ini-1' } },
      body: { step: 'tech', reason: 'build stopped: verify failed: make test exited 2' },
    });
    expect(done).toHaveBeenCalledWith('tech');
    expect($poll.get()).toBe(before + 1);
  });

  it('AC3: a refusal shows its detail (then title, then fixed text), keeps tech, no tick', async () => {
    POST.mockResolvedValueOnce({ error: { detail: 'step is not reopenable' } });
    open({ d: make() });
    const before = $poll.get();
    fireEvent.click(screen.getByLabelText('1.4 tech · tech-lead'));
    fireEvent.click(confirm());
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe('step is not reopenable'),
    );
    expect((screen.getByLabelText('1.4 tech · tech-lead') as HTMLInputElement).checked).toBe(true);
    expect($poll.get()).toBe(before);
    POST.mockResolvedValueOnce({ error: { title: 'T' } });
    fireEvent.click(confirm());
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('T'));
    POST.mockResolvedValueOnce({ error: {} });
    fireEvent.click(confirm());
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe('The step was not reopened.'),
    );
  });

  it('a throw gives the fixed line and keeps the modal', async () => {
    POST.mockRejectedValueOnce(new Error('net'));
    open({ d: make() });
    fireEvent.click(screen.getByLabelText('1.1 intake · intake-router'));
    fireEvent.click(confirm());
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe('The step was not reopened.'),
    );
    expect(confirm().disabled).toBe(false);
  });

  it('AC4: Escape closes, posts nothing, focus returns to the opener', () => {
    const opener = open({ d: make() });
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(POST).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(opener);
  });

  it('AC4: Tab from the last enabled control wraps to the first', () => {
    open({ d: make() });
    const panel = screen.getByRole('dialog');
    fireEvent.click(screen.getByLabelText('1.4 tech · tech-lead'));
    confirm().focus();
    fireEvent.keyDown(panel, { key: 'Tab' });
    expect(document.activeElement).toBe(screen.getByLabelText('1.1 intake · intake-router'));
  });

  it('AC6: advance origin, with and without a live Run', () => {
    open({ d: make({ reason: 'preflight: harness: not ready' }), origin: 'advance', runId: null });
    expect(text()).toContain('Which spec step does this stop come from?');
    expect(text()).toContain('first turn: "advance blocked: preflight: harness: not ready"');
    expect(text()).toContain('The step you choose reopens as round 2');
    expect(text()).not.toContain('is cancelled');
    cleanup();
    open({ d: make({ reason: 'preflight: x' }), origin: 'advance', runId: RUN_B });
    expect(text()).toContain('Run 0193…bb02 is cancelled and keeps its page.');
  });

  it('its lines are frozen at mount: a later detail does not change them', () => {
    const { rerender } = render(
      h(ReopenStepModal, {
        detail: make(),
        origin: 'build',
        runId: RUN_B,
        onClose: () => {},
        onReopened: () => {},
      }),
    );
    rerender(
      h(ReopenStepModal, {
        detail: make({ reason: 'other', round: 5 } as never),
        origin: 'build',
        runId: RUN_B,
        onClose: () => {},
        onReopened: () => {},
      }),
    );
    expect(text()).toContain('verify failed: make test exited 2');
    expect(text()).toContain('round 2');
  });

  it('Escape and the scrim do not dismiss while the post is in flight; the primary is disabled', async () => {
    let resolve: (v: unknown) => void = () => {};
    POST.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    open({ d: make() });
    fireEvent.click(screen.getByLabelText('1.2 product · product-lead'));
    fireEvent.click(confirm());
    await waitFor(() => expect(confirm().disabled).toBe(true));
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    fireEvent.click(document.querySelector('.ini-plane-scrim') as HTMLElement);
    expect(screen.getByRole('dialog')).toBeTruthy();
    resolve({ error: { detail: 'refused' } });
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('refused'));
  });

  it('the scrim dismisses when idle', () => {
    open({ d: make() });
    fireEvent.click(document.querySelector('.ini-plane-scrim') as HTMLElement);
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
