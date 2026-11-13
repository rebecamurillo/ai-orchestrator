// @vitest-environment jsdom
/** `RunTitle` (epic 3 story 3, AC2): the Run label as the title, edited in place. */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import RunTitle from '../../src/components/run/RunTitle';

afterEach(cleanup);

const LABEL = 'familio familio-snake-v2 bench-v1-staged 2026-11-10 10:23';

function mount(over: Record<string, unknown> = {}) {
  const onSave = vi.fn().mockResolvedValue(null);
  const view = render(
    createElement(RunTitle, { label: LABEL, byOperator: false, onSave, ...over } as never),
  );
  return { onSave, ...view };
}
const input = () => screen.getByLabelText('Run label') as HTMLInputElement;
const title = () => screen.getByTestId('wf-title').textContent;

describe('RunTitle', () => {
  it('reads the label and names a default one', () => {
    mount();
    expect(title()).toBe(LABEL);
    expect(screen.getByText('default label')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'edit label' })).toBeTruthy();
  });

  it('names an operator label and how to clear it', () => {
    mount({ byOperator: true });
    expect(screen.getByText('your label · clear it to restore the default')).toBeTruthy();
  });

  it('opens a focused 120-character input holding the label', () => {
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'edit label' }));
    expect(input().value).toBe(LABEL);
    expect(input().maxLength).toBe(120);
    expect(document.activeElement).toBe(input());
    expect(screen.getByRole('button', { name: 'save label' })).toBeTruthy();
  });

  it('Enter saves the typed text once, closes and shows it', async () => {
    const { onSave } = mount();
    fireEvent.click(screen.getByRole('button', { name: 'edit label' }));
    fireEvent.change(input(), { target: { value: 'snake round 1' } });
    fireEvent.keyDown(input(), { key: 'Enter' });
    await waitFor(() => expect(title()).toBe('snake round 1'));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith('snake round 1');
    expect(screen.queryByLabelText('Run label')).toBeNull();
  });

  it('the save button saves too', async () => {
    const { onSave } = mount();
    fireEvent.click(screen.getByRole('button', { name: 'edit label' }));
    fireEvent.change(input(), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'save label' }));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith('x'));
  });

  it('clearing the field and pressing Enter restores the default (null)', async () => {
    const { onSave } = mount({ byOperator: true });
    fireEvent.click(screen.getByRole('button', { name: 'edit label' }));
    fireEvent.change(input(), { target: { value: '' } });
    fireEvent.keyDown(input(), { key: 'Enter' });
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(null));
    await waitFor(() => expect(screen.queryByLabelText('Run label')).toBeNull());
    expect(title()).toBe(LABEL);
  });

  it('Escape sends nothing and keeps the title', () => {
    const { onSave } = mount();
    fireEvent.click(screen.getByRole('button', { name: 'edit label' }));
    fireEvent.change(input(), { target: { value: 'typed' } });
    fireEvent.keyDown(input(), { key: 'Escape' });
    expect(onSave).not.toHaveBeenCalled();
    expect(title()).toBe(LABEL);
    expect(screen.queryByLabelText('Run label')).toBeNull();
  });

  it('ignores other keys', () => {
    const { onSave } = mount();
    fireEvent.click(screen.getByRole('button', { name: 'edit label' }));
    fireEvent.keyDown(input(), { key: 'a' });
    expect(onSave).not.toHaveBeenCalled();
    expect(input()).toBeTruthy();
  });

  it('a refused save keeps the input open and shows the detail, or the title', async () => {
    const onSave = vi
      .fn()
      .mockResolvedValueOnce({
        status: 422,
        title: 'invalid',
        type: 'x',
        detail: 'label must be 1-120 characters',
      })
      .mockResolvedValueOnce({ status: 500, title: 'broken', type: 'x' });
    mount({ onSave });
    fireEvent.click(screen.getByRole('button', { name: 'edit label' }));
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(await screen.findByText('label must be 1-120 characters')).toBeTruthy();
    expect(input()).toBeTruthy();
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(await screen.findByText('broken')).toBeTruthy();
  });

  it('takes a new label prop over the locally shown text', async () => {
    const { rerender, onSave } = mount();
    fireEvent.click(screen.getByRole('button', { name: 'edit label' }));
    fireEvent.change(input(), { target: { value: 'mine' } });
    fireEvent.keyDown(input(), { key: 'Enter' });
    await waitFor(() => expect(title()).toBe('mine'));
    rerender(createElement(RunTitle, { label: 'server', byOperator: true, onSave } as never));
    expect(title()).toBe('server');
  });
});
