// @vitest-environment jsdom
/** Story 11.4: the cancel-initiative confirmation. */
import { createElement as h, useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { POST } = vi.hoisted(() => ({ POST: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { POST } }));

import CancelInitiativeModal from '../../src/components/initiative/CancelInitiativeModal';
import { $poll } from '../../src/stores/poll';
import { detail, step, workflow, type Detail } from './initiative-fixtures';

const session = { workflow: 'spec', step: 'ux', kind: 'session', state: 'open', id: 's1' };

function make(over: Partial<Detail> = {}, run_id: string | null = null): Detail {
  return detail({
    sessions: [],
    workflows: [
      workflow('spec', 1, { steps: [step('ux')], run_id }),
      workflow('build', 2, { type: 'auto' }),
    ],
    ...over,
  } as Partial<Detail>);
}

function Host({ d }: { d: Detail }) {
  const [open, setOpen] = useState(false);
  return h(
    'div',
    null,
    h('button', { 'data-testid': 'opener', onClick: () => setOpen(true) }, 'open'),
    open ? h(CancelInitiativeModal, { detail: d, onClose: () => setOpen(false) }) : null,
  );
}

function open(d: Detail) {
  render(h(Host, { d }));
  const opener = screen.getByTestId('opener');
  opener.focus();
  fireEvent.click(opener);
  return opener;
}

const items = () => Array.from(document.querySelectorAll('li')).map((li) => li.textContent);

beforeEach(() => POST.mockReset());
afterEach(cleanup);

describe('CancelInitiativeModal', () => {
  it('lists four lines with the open session; Keep it holds focus', () => {
    open(make({ sessions: [session] } as Partial<Detail>));
    expect(screen.getByRole('dialog', { name: 'CANCEL INITIATIVE' })).toBeTruthy();
    expect(screen.getByText('Cancel familio-dessin-v2?')).toBeTruthy();
    expect(items()).toEqual([
      'spec/familio-dessin-v2 is deleted',
      'The open ux session is cancelled',
      'Files already merged into main stay; nothing is removed from main',
      'The slug familio-dessin-v2 is free again',
    ]);
    expect(document.activeElement).toBe(screen.getByText('Keep it'));
  });

  it('names the Run when no session is open', () => {
    open(make({}, '0193e5f6-0000-7000-8000-000000008c02'));
    expect(items()[1]).toBe('Run 0193…8c02 is cancelled');
  });

  it('lists three lines when there is neither', () => {
    open(make());
    expect(items()).toHaveLength(3);
  });

  it('Escape closes, posts nothing, focus returns to the opener', () => {
    const opener = open(make());
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(POST).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(opener);
  });

  it('Tab wraps inside the plane', () => {
    open(make());
    const panel = screen.getByRole('dialog');
    screen.getByTestId('ini-cancel-confirm').focus();
    fireEvent.keyDown(panel, { key: 'Tab' });
    expect(document.activeElement).toBe(screen.getByText('Keep it'));
    fireEvent.keyDown(panel, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(screen.getByTestId('ini-cancel-confirm'));
  });

  it('posts once, closes and ticks on 2xx', async () => {
    POST.mockResolvedValue({ response: { status: 200 } });
    open(make());
    const before = $poll.get();
    fireEvent.click(screen.getByTestId('ini-cancel-confirm'));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(POST).toHaveBeenCalledTimes(1);
    expect(POST).toHaveBeenCalledWith('/initiatives/{initiative_id}/cancel', {
      params: { path: { initiative_id: 'ini-1' } },
    });
    expect($poll.get()).toBe(before + 1);
  });

  it('Escape and the scrim do not dismiss while the post is in flight', async () => {
    let resolve: (v: unknown) => void = () => {};
    POST.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    open(make());
    fireEvent.click(screen.getByTestId('ini-cancel-confirm'));
    await waitFor(() =>
      expect((screen.getByTestId('ini-cancel-confirm') as HTMLButtonElement).disabled).toBe(true),
    );
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    fireEvent.click(document.querySelector('.ini-plane-scrim') as HTMLElement);
    expect(screen.getByRole('dialog')).toBeTruthy();
    resolve({ error: { detail: 'refused' } });
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('refused'));
  });

  it('renders a refusal and stays open; falls back to title, fixed text, and throw', async () => {
    POST.mockResolvedValueOnce({ error: { detail: 'nope' } });
    open(make());
    fireEvent.click(screen.getByTestId('ini-cancel-confirm'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('nope'));
    expect(screen.getByRole('dialog')).toBeTruthy();
    POST.mockResolvedValueOnce({ error: { title: 'T' } });
    fireEvent.click(screen.getByTestId('ini-cancel-confirm'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('T'));
    POST.mockResolvedValueOnce({ error: {} });
    fireEvent.click(screen.getByTestId('ini-cancel-confirm'));
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe('The initiative was not cancelled.'),
    );
    POST.mockRejectedValueOnce(new Error('net'));
    fireEvent.click(screen.getByTestId('ini-cancel-confirm'));
    await waitFor(() => expect(POST).toHaveBeenCalledTimes(4));
    expect(screen.getByRole('alert').textContent).toBe('The initiative was not cancelled.');
  });
});
