// @vitest-environment jsdom
/** Story 11.2: the Composer posts the operator's message and never closes a step. */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { POST } = vi.hoisted(() => ({ POST: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { POST } }));

import Composer from '../../src/components/initiative/Composer';
import { $poll } from '../../src/stores/poll';

const mount = () => render(createElement(Composer, { runId: 'run-1', hint: 'the hint' }));
const box = () => screen.getByTestId('ini-message') as HTMLTextAreaElement;
const type = (text: string) => fireEvent.change(box(), { target: { value: text } });

beforeEach(() => POST.mockReset());
afterEach(cleanup);

describe('Composer', () => {
  it('renders the label, the hint and an enabled Send', () => {
    mount();
    expect(screen.getByLabelText('message')).toBe(box());
    expect(document.body.textContent).toContain('the hint');
    expect((screen.getByTestId('ini-send') as HTMLButtonElement).disabled).toBe(false);
  });

  it('Enter alone posts nothing and is not prevented', () => {
    mount();
    type('hello');
    const notPrevented = fireEvent.keyDown(box(), { key: 'Enter' });
    expect(notPrevented).toBe(true);
    expect(POST).not.toHaveBeenCalled();
  });

  it.each([{ ctrlKey: true }, { metaKey: true }])('%o sends once', async (mods) => {
    POST.mockResolvedValue({ response: { status: 202 } });
    mount();
    type('  hello  ');
    const before = $poll.get();
    fireEvent.keyDown(box(), { key: 'Enter', ...mods });
    await waitFor(() => expect(box().value).toBe(''));
    expect(POST).toHaveBeenCalledTimes(1);
    expect(POST).toHaveBeenCalledWith('/runs/{run_id}/session/messages', {
      params: { path: { run_id: 'run-1' } },
      body: { text: 'hello' },
    });
    expect($poll.get()).toBe(before + 1);
  });

  it('Send click posts; empty text posts nothing', async () => {
    POST.mockResolvedValue({ response: { status: 202 } });
    mount();
    fireEvent.click(screen.getByTestId('ini-send'));
    expect(POST).not.toHaveBeenCalled();
    type('hi');
    fireEvent.click(screen.getByTestId('ini-send'));
    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
  });

  it('shows the refusal detail and keeps the text; falls back to the title', async () => {
    POST.mockResolvedValueOnce({ error: { detail: 'no way', title: 'T' } });
    mount();
    type('keep me');
    fireEvent.click(screen.getByTestId('ini-send'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('no way'));
    expect(box().value).toBe('keep me');
    POST.mockResolvedValueOnce({ error: { title: 'Title only' } });
    fireEvent.click(screen.getByTestId('ini-send'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Title only'));
  });

  it('clears an earlier error on success and disables Send only while posting', async () => {
    let resolve: (v: unknown) => void = () => {};
    POST.mockResolvedValueOnce({ error: { detail: 'bad' } });
    mount();
    type('a');
    fireEvent.click(screen.getByTestId('ini-send'));
    await waitFor(() => screen.getByRole('alert'));
    POST.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    fireEvent.click(screen.getByTestId('ini-send'));
    await waitFor(() =>
      expect((screen.getByTestId('ini-send') as HTMLButtonElement).disabled).toBe(true),
    );
    fireEvent.click(screen.getByTestId('ini-send'));
    expect(POST).toHaveBeenCalledTimes(2);
    resolve({ response: { status: 202 } });
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect((screen.getByTestId('ini-send') as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('Composer without a hint (story 11.5, 2026-11-26: the merge composer)', () => {
  it('renders no hint paragraph for an empty hint', () => {
    render(createElement(Composer, { runId: 'run-1', hint: '' }));
    expect(document.querySelector('.ini-hint')).toBeNull();
    expect(box()).toBeTruthy();
  });
});
