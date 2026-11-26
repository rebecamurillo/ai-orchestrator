// @vitest-environment jsdom
/** Story 11.4: the forced-start confirmation and the shared ConfirmPlane frame. */
import { createElement as h, useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { POST } = vi.hoisted(() => ({ POST: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { POST } }));

import ConfirmPlane from '../../src/components/initiative/ConfirmPlane';
import ForceStartModal from '../../src/components/initiative/ForceStartModal';
import { $poll } from '../../src/stores/poll';

function Host({ nextWorkflow = 'build' as string | null }) {
  const [open, setOpen] = useState(false);
  return h(
    'div',
    null,
    h('button', { 'data-testid': 'opener', onClick: () => setOpen(true) }, 'open'),
    open
      ? h(ForceStartModal, {
          initiativeId: 'ini-1',
          current: 'ux',
          next: 'tech',
          parkSeq: 7,
          slug: 'familio-dessin-v2',
          workflow: 'spec',
          nextWorkflow,
          onClose: () => setOpen(false),
        })
      : null,
  );
}

function open(props = {}) {
  render(h(Host, props));
  const opener = screen.getByTestId('opener');
  opener.focus();
  fireEvent.click(opener);
  return opener;
}

beforeEach(() => POST.mockReset());
afterEach(cleanup);

describe('ForceStartModal', () => {
  it('states the head, question and mechanism; focus is on Keep', () => {
    open();
    expect(screen.getByRole('dialog').getAttribute('aria-modal')).toBe('true');
    expect(screen.getByRole('dialog', { name: 'START TECH NOW' })).toBeTruthy();
    const text = screen.getByRole('dialog').textContent ?? '';
    expect(text).toContain('Are you sure? If step «UX» is not done this workflow might fail.');
    expect(text).toContain(
      'The UX step closes as skipped, forced; its conversation and its draft files are kept. Tech starts with what is on spec/familio-dessin-v2 now. The gate is never forced, so build cannot start before spec passes it.',
    );
    expect(document.activeElement).toBe(screen.getByText('Keep ux open'));
    expect(screen.getByTestId('ini-force-confirm').textContent).toBe('Start tech');
  });

  it('ends the mechanism at the files when no workflow follows', () => {
    open({ nextWorkflow: null });
    expect(screen.getByRole('dialog').textContent).not.toContain('The gate is never forced');
  });

  it('Escape closes, posts nothing and returns focus to the opener', () => {
    const opener = open();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(POST).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(opener);
  });

  it('the scrim acts as Keep', () => {
    const opener = open();
    fireEvent.click(document.querySelector('.ini-plane-scrim') as HTMLElement);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(POST).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(opener);
  });

  it('Tab and Shift+Tab wrap inside the plane', () => {
    open();
    const panel = screen.getByRole('dialog');
    const keep = screen.getByText('Keep ux open');
    const start = screen.getByTestId('ini-force-confirm');
    start.focus();
    fireEvent.keyDown(panel, { key: 'Tab' });
    expect(document.activeElement).toBe(keep);
    fireEvent.keyDown(panel, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(start);
    keep.focus();
    expect(fireEvent.keyDown(panel, { key: 'Tab' })).toBe(true);
    (document.body as HTMLElement).focus();
    (screen.getByTestId('opener') as HTMLElement).focus();
    fireEvent.keyDown(panel, { key: 'Tab' });
    expect(document.activeElement).toBe(keep);
    (screen.getByTestId('opener') as HTMLElement).focus();
    fireEvent.keyDown(panel, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(start);
    fireEvent.keyDown(panel, { key: 'a' });
  });

  it('posts once with the park_seq, closes and ticks', async () => {
    POST.mockResolvedValue({ response: { status: 200 } });
    open();
    const before = $poll.get();
    fireEvent.click(screen.getByTestId('ini-force-confirm'));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(POST).toHaveBeenCalledTimes(1);
    expect(POST).toHaveBeenCalledWith('/initiatives/{initiative_id}/start-next', {
      params: { path: { initiative_id: 'ini-1' } },
      body: { park_seq: 7 },
    });
    expect($poll.get()).toBe(before + 1);
  });

  it('shows a refusal detail, stays open, does not tick, and disables while in flight', async () => {
    let resolve: (v: unknown) => void = () => {};
    POST.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    open();
    const before = $poll.get();
    fireEvent.click(screen.getByTestId('ini-force-confirm'));
    await waitFor(() =>
      expect((screen.getByTestId('ini-force-confirm') as HTMLButtonElement).disabled).toBe(true),
    );
    expect((screen.getByText('Keep ux open') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId('ini-force-confirm'));
    resolve({ error: { detail: 'start-next refused: the next step is not a conversation step' } });
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(
        'start-next refused: the next step is not a conversation step',
      ),
    );
    expect(POST).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect($poll.get()).toBe(before);
    expect((screen.getByTestId('ini-force-confirm') as HTMLButtonElement).disabled).toBe(false);
  });

  it('Escape and the scrim do not dismiss while the post is in flight', async () => {
    let resolve: (v: unknown) => void = () => {};
    POST.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    open();
    fireEvent.click(screen.getByTestId('ini-force-confirm'));
    await waitFor(() =>
      expect((screen.getByTestId('ini-force-confirm') as HTMLButtonElement).disabled).toBe(true),
    );
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    fireEvent.click(document.querySelector('.ini-plane-scrim') as HTMLElement);
    expect(screen.getByRole('dialog')).toBeTruthy();
    resolve({ error: { detail: 'refused' } });
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('refused'));
  });

  it('falls back to the title, and to a fixed text when the post throws', async () => {
    POST.mockResolvedValueOnce({ error: { title: 'Conflict' } });
    open();
    fireEvent.click(screen.getByTestId('ini-force-confirm'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Conflict'));
    POST.mockResolvedValueOnce({ error: {} });
    fireEvent.click(screen.getByTestId('ini-force-confirm'));
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe('The step was not started.'),
    );
    POST.mockRejectedValueOnce(new Error('net'));
    fireEvent.click(screen.getByTestId('ini-force-confirm'));
    await waitFor(() => expect(POST).toHaveBeenCalledTimes(3));
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe('The step was not started.'),
    );
  });
});

describe('ConfirmPlane', () => {
  it('returns focus to the opener when it unmounts', () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const view = render(
      h(ConfirmPlane, {
        labelId: 'x',
        head: 'H',
        onDismiss: () => {},
        children: h('button', { 'data-autofocus': true }, 'ok'),
      }),
    );
    expect(document.activeElement).toBe(screen.getByText('ok'));
    view.unmount();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });

  it('ignores Tab when nothing inside is focusable', () => {
    render(
      h(ConfirmPlane, {
        labelId: 'x',
        head: 'H',
        onDismiss: () => {},
        children: h('span', null, 'none'),
      }),
    );
    expect(fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Tab' })).toBe(true);
  });
});
