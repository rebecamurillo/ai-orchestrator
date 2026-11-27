// @vitest-environment jsdom
/** Story 11.5: the missing-budget answer (AC6). */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET, PUT } = vi.hoisted(() => ({ GET: vi.fn(), PUT: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET, PUT } }));

import BudgetStop from '../../src/components/initiative/BudgetStop';
import { $poll } from '../../src/stores/poll';

const field = () => screen.getByTestId('ini-budget') as HTMLInputElement;
const button = () => screen.getByTestId('ini-budget-set') as HTMLButtonElement;
const type = (v: string) => fireEvent.change(field(), { target: { value: v } });
const project = {
  default_harness: 'claude',
  default_model: null,
  default_autonomy: 'auto',
  default_senior_model: 'opus',
};

beforeEach(() => {
  GET.mockReset();
  PUT.mockReset();
  render(createElement(BudgetStop, { projectId: 'p1' }));
});
afterEach(cleanup);

describe('BudgetStop', () => {
  it('starts empty and disabled, with its label', () => {
    expect(screen.getByLabelText('budget USD')).toBe(field());
    expect(field().type).toBe('number');
    expect(field().value).toBe('');
    expect(button().disabled).toBe(true);
    expect(button().textContent).toBe('Set project budget and start');
  });

  it.each(['0', '-5', '12.345', 'abc'])('stays disabled for %s', (v) => {
    type(v);
    expect(button().disabled).toBe(true);
  });

  it('reads the project, then replaces all five defaults once and refreshes', async () => {
    GET.mockResolvedValue({ data: project });
    PUT.mockResolvedValue({ data: {} });
    const tick = $poll.get();
    type('60');
    expect(button().disabled).toBe(false);
    fireEvent.click(button());
    await waitFor(() => expect($poll.get()).toBe(tick + 1));
    expect(GET).toHaveBeenCalledWith('/projects/{project_id}', {
      params: { path: { project_id: 'p1' } },
    });
    expect(PUT).toHaveBeenCalledTimes(1);
    expect(PUT).toHaveBeenCalledWith('/projects/{project_id}/run-defaults', {
      params: { path: { project_id: 'p1' } },
      body: {
        default_budget_usd: '60',
        default_harness: 'claude',
        default_model: null,
        default_autonomy: 'auto',
        default_senior_model: 'opus',
      },
    });
  });

  it('shows a refused read and does not put or refresh', async () => {
    GET.mockResolvedValue({ error: { detail: 'no such project' } });
    const tick = $poll.get();
    type('60');
    fireEvent.click(button());
    expect((await screen.findByRole('alert')).textContent).toBe('no such project');
    expect(PUT).not.toHaveBeenCalled();
    expect($poll.get()).toBe(tick);
  });

  it('shows a refused put and does not refresh', async () => {
    GET.mockResolvedValue({ data: project });
    PUT.mockResolvedValue({ error: { title: 'Conflict' } });
    const tick = $poll.get();
    type('60.5');
    fireEvent.click(button());
    expect((await screen.findByRole('alert')).textContent).toBe('Conflict');
    expect($poll.get()).toBe(tick);
  });

  it('reports a thrown request', async () => {
    GET.mockRejectedValue(new Error('down'));
    type('60');
    fireEvent.click(button());
    expect((await screen.findByRole('alert')).textContent).toBe('The budget was not saved.');
  });
});

describe('BudgetStop after the answer (review, 2026-11-26)', () => {
  it('stays disabled after a saved budget, so the advance is asked once', async () => {
    GET.mockResolvedValue({ data: project });
    PUT.mockResolvedValue({ data: {} });
    const tick = $poll.get();
    type('60');
    fireEvent.click(button());
    await waitFor(() => expect($poll.get()).toBe(tick + 1));
    expect(button().disabled).toBe(true);
  });

  it('re-enables after a refused put', async () => {
    GET.mockResolvedValue({ data: project });
    PUT.mockResolvedValue({ error: { detail: 'no' } });
    type('60');
    fireEvent.click(button());
    await screen.findByRole('alert');
    expect(button().disabled).toBe(false);
  });
});
