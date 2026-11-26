// @vitest-environment jsdom
/** Story 11.1: the Initiative page island against a mocked `src/api/client.ts` (AC5–AC7, AC10). */
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import InitiativePage from '../../src/islands/InitiativePage';
import { forceTick, stopPolling } from '../../src/stores/poll';
import { detail, step, workflow, type Detail } from './initiative-fixtures';

const ok = (data: Detail) => ({ data, response: { status: 200 } });
const mount = (initialWorkflow: number | null = null) =>
  render(createElement(InitiativePage, { initiativeId: 'ini-1', initialWorkflow }));

const initiativeCalls = () => GET.mock.calls.filter((c) => c[0] === '/initiatives/{initiative_id}');

beforeEach(() => {
  GET.mockReset();
});
afterEach(() => {
  stopPolling();
  cleanup();
  document.body.innerHTML = '';
});

describe('InitiativePage load', () => {
  it('sends opened=true, selects the current workflow and step, renders strip and conversation', async () => {
    GET.mockResolvedValue(ok(detail()));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-steps')).toBeTruthy());
    expect(GET).toHaveBeenCalledWith('/initiatives/{initiative_id}', {
      params: { path: { initiative_id: 'ini-1' }, query: { opened: true } },
    });
    expect(screen.getByTestId('ini-header')).toBeTruthy();
    expect(screen.getByTestId('ini-step-ux').getAttribute('data-selected')).toBe('true');
    expect(screen.getByTestId('ini-conversation')).toBeTruthy();
    expect(screen.getByTestId('ini-workflow-spec').getAttribute('aria-pressed')).toBe('true');
  });

  it('selects the named workflow: no strip, the auto summary in the main column', async () => {
    GET.mockImplementation(async (path: string) =>
      path === '/initiatives/{initiative_id}'
        ? ok(detail())
        : { data: { id: 'p1', default_budget_usd: '60.00' }, response: { status: 200 } },
    );
    mount(2);
    await waitFor(() => expect(screen.getByTestId('ini-workflow-build')).toBeTruthy());
    expect(screen.getByTestId('ini-workflow-build').getAttribute('aria-pressed')).toBe('true');
    expect(screen.queryByTestId('ini-steps')).toBeNull();
    expect(screen.queryByTestId('ini-conversation')).toBeNull();
    await waitFor(() => expect(screen.getByTestId('ini-summary')).toBeTruthy());
    expect(document.body.textContent).toContain('starts by itself when spec is done');
  });
});

describe('InitiativePage polling', () => {
  it('keeps the selection across a poll and sends no opened', async () => {
    GET.mockResolvedValue(ok(detail()));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-step-product')).toBeTruthy());
    fireEvent.click(screen.getByTestId('ini-step-product'));
    expect(screen.getByTestId('ini-step-product').getAttribute('data-selected')).toBe('true');

    act(() => forceTick());
    await waitFor(() => expect(initiativeCalls()).toHaveLength(2));
    expect(initiativeCalls()[1][1]).toEqual({ params: { path: { initiative_id: 'ini-1' } } });
    await act(async () => {});
    expect(screen.getByTestId('ini-step-product').getAttribute('data-selected')).toBe('true');
    expect(screen.getByTestId('ini-step-ux').getAttribute('data-selected')).toBeNull();
    expect(screen.getByTestId('ini-workflow-spec').getAttribute('aria-pressed')).toBe('true');
  });

  it('renders FailedFetch with the request path when a poll fails', async () => {
    GET.mockResolvedValueOnce(ok(detail()));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-steps')).toBeTruthy());
    GET.mockResolvedValueOnce({ error: {}, response: { status: 500 } });
    act(() => forceTick());
    await waitFor(() => expect(screen.getByTestId('fetch-failed')).toBeTruthy());
    expect(document.body.textContent).toContain('/api/initiatives/ini-1');
  });

  it('renders FailedFetch when the request throws', async () => {
    GET.mockRejectedValueOnce(new Error('down'));
    mount();
    await waitFor(() => expect(screen.getByTestId('fetch-failed')).toBeTruthy());
  });

  it('still sends opened=true on the Retry after a failed load', async () => {
    GET.mockResolvedValueOnce({ error: {}, response: { status: 500 } });
    mount();
    await waitFor(() => expect(screen.getByTestId('fetch-failed')).toBeTruthy());
    GET.mockResolvedValue(ok(detail()));
    act(() => forceTick());
    await waitFor(() => expect(screen.getByTestId('ini-steps')).toBeTruthy());
    expect(initiativeCalls()[1][1]).toEqual({
      params: { path: { initiative_id: 'ini-1' }, query: { opened: true } },
    });
    act(() => forceTick());
    await waitFor(() => expect(initiativeCalls()).toHaveLength(3));
    expect(initiativeCalls()[2][1]).toEqual({ params: { path: { initiative_id: 'ini-1' } } });
  });

  it('ignores an older answer that arrives last', async () => {
    let resolveFirst: (v: unknown) => void = () => {};
    GET.mockImplementationOnce(() => new Promise((r) => (resolveFirst = r)));
    mount();
    GET.mockResolvedValueOnce(ok(detail({ step: 'ux' })));
    act(() => forceTick());
    await waitFor(() => expect(screen.getByTestId('ini-steps')).toBeTruthy());
    await act(async () => {
      resolveFirst(ok(detail({ workflow: 'stale', current_position: 2 })));
    });
    expect(screen.getByTestId('ini-workflow-spec').getAttribute('aria-pressed')).toBe('true');
    expect(document.body.textContent).not.toContain('stale');
  });
});

describe('InitiativePage selection', () => {
  it('selects a workflow cell and shows the auto summary, then back to the strip', async () => {
    GET.mockImplementation(async (path: string) =>
      path === '/initiatives/{initiative_id}'
        ? ok(detail())
        : { data: { id: 'p1', default_budget_usd: null }, response: { status: 200 } },
    );
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-steps')).toBeTruthy());
    fireEvent.click(screen.getByTestId('ini-workflow-build'));
    expect(screen.queryByTestId('ini-steps')).toBeNull();
    fireEvent.click(screen.getByTestId('ini-workflow-spec'));
    expect(screen.getByTestId('ini-step-ux').getAttribute('data-selected')).toBe('true');
  });

  it('shows no step selection for an interactive workflow that is not current', async () => {
    const d = detail({
      current_position: 2,
      workflow: 'ship',
      current_step: 'ux',
      workflows: [
        workflow('spec', 1, { steps: [step('product')] }),
        workflow('ship', 2, { steps: [step('ux')] }),
      ],
    });
    GET.mockResolvedValue(ok(d));
    mount(1);
    await waitFor(() => expect(screen.getByTestId('ini-step-product')).toBeTruthy());
    expect(screen.getByTestId('ini-step-product').getAttribute('data-selected')).toBeNull();
    expect(screen.getByTestId('ini-conversation')).toBeTruthy();
    fireEvent.click(screen.getByTestId('ini-workflow-ship'));
    expect(screen.getByTestId('ini-step-ux').getAttribute('aria-current')).toBe('step');
  });
});

describe('InitiativePage automatic step', () => {
  const withAuto = (turns: unknown[]) => {
    const d = detail();
    d.workflows[0].steps[3] = step('plan', {
      kind: 'automatic',
      line: 'verify green',
      token: 'DON',
      turns,
    } as never);
    return d;
  };

  it('shows the step line and a log link to the last attempt', async () => {
    GET.mockResolvedValue(
      ok(
        withAuto([
          { run_id: 'r1', attempt_id: 'a0' },
          { run_id: 'r1', attempt_id: 'a1' },
        ]),
      ),
    );
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-step-plan')).toBeTruthy());
    fireEvent.click(screen.getByTestId('ini-step-plan'));
    expect(screen.getByTestId('ini-auto-step').textContent).toContain('verify green');
    expect(screen.getByTestId('ini-step-log').getAttribute('href')).toBe(
      '/api/runs/r1/attempts/a1/log',
    );
    expect(screen.queryByTestId('ini-conversation')).toBeNull();
  });

  it('shows no log link without a turn', async () => {
    GET.mockResolvedValue(ok(withAuto([])));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-step-plan')).toBeTruthy());
    fireEvent.click(screen.getByTestId('ini-step-plan'));
    expect(screen.getByTestId('ini-auto-step').textContent).toContain('verify green');
    expect(screen.queryByTestId('ini-step-log')).toBeNull();
  });
});
