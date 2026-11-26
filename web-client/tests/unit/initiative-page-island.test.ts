// @vitest-environment jsdom
/** Story 11.1: the Initiative page island against a mocked `src/api/client.ts` (AC5–AC7, AC10). */
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET, POST } = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET, POST } }));

import InitiativePage from '../../src/islands/InitiativePage';
import { forceTick, stopPolling } from '../../src/stores/poll';
import { convStep, file, turn } from './conversation-fixtures';
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

/* Story 11.2 (2026-11-26): the conversation region is filled. */
describe('InitiativePage conversation', () => {
  const withConversation = (techStatus: 'planned' | 'running', current = 'ux') => {
    const d = detail({ current_step: current, step: current });
    d.workflows[0].steps[2] = convStep({
      token: 'DON',
      status: 'done',
      files: [file('DESIGN.md'), file('EXPERIENCE.md')],
      turns: [turn(1)],
    });
    d.workflows[0].steps[3] = step('tech', {
      status: techStatus,
      token: techStatus === 'running' ? 'RUN' : 'QUE',
    });
    return d;
  };

  it('open tech selects tech; a poll with tech current keeps ux selected', async () => {
    GET.mockResolvedValue(ok(withConversation('running')));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-conversation')).toBeTruthy());
    expect(screen.getByTestId('ini-step-ux').getAttribute('data-selected')).toBe('true');
    GET.mockResolvedValue(ok(withConversation('running', 'tech')));
    act(() => forceTick());
    await waitFor(() => expect(initiativeCalls()).toHaveLength(2));
    await act(async () => {});
    expect(screen.getByTestId('ini-step-ux').getAttribute('data-selected')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'open tech' }));
    expect(screen.getByTestId('ini-step-tech').getAttribute('data-selected')).toBe('true');
  });

  it('keeps the typed text across a poll; no composer on a step that is not current', async () => {
    const d = detail();
    d.workflows[0].steps[2] = convStep({ files: [file('DESIGN.md'), file('EXPERIENCE.md')] });
    GET.mockResolvedValue(ok(d));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-message')).toBeTruthy());
    fireEvent.change(screen.getByTestId('ini-message'), { target: { value: 'draft' } });
    act(() => forceTick());
    await waitFor(() => expect(initiativeCalls()).toHaveLength(2));
    await act(async () => {});
    expect((screen.getByTestId('ini-message') as HTMLTextAreaElement).value).toBe('draft');
    expect(document.body.textContent).toContain(
      'Say you are done in your own words; the agent confirms in one line and writes DESIGN.md, EXPERIENCE.md. The step closes when the file holds its done content.',
    );
    fireEvent.click(screen.getByTestId('ini-step-product'));
    expect(screen.queryByTestId('ini-message')).toBeNull();
    expect(document.body.innerHTML).not.toMatch(/step_close|session_end|skip_step/);
  });

  it('show all does not carry over to another selected step', async () => {
    const d = detail();
    const turns = [1, 2, 3, 4, 5].map((n) => turn(n));
    d.workflows[0].steps[0] = convStep({ id: 'product', token: 'DON', status: 'done', turns });
    d.workflows[0].steps[1] = convStep({ id: 'arch', token: 'DON', status: 'done', turns });
    GET.mockResolvedValue(ok(d));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-step-product')).toBeTruthy());
    fireEvent.click(screen.getByTestId('ini-step-product'));
    fireEvent.click(screen.getByRole('button', { name: 'show all 5 turns' }));
    expect(screen.getAllByTestId(/^ini-turn-/)).toHaveLength(5);
    fireEvent.click(screen.getByTestId('ini-step-arch'));
    expect(screen.getAllByTestId(/^ini-turn-/)).toHaveLength(3);
    expect(screen.getByRole('button', { name: 'show all 5 turns' })).toBeTruthy();
  });

  it('renders no composer for a cancelled initiative', async () => {
    const d = detail({ status: 'cancelled' });
    d.workflows[0].steps[2] = convStep();
    GET.mockResolvedValue(ok(d));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-conversation-head')).toBeTruthy());
    expect(screen.queryByTestId('ini-message')).toBeNull();
  });
});

/** Story 11.3 (2026-11-22): the right column is mounted (AC9). */
describe('InitiativePage right column', () => {
  it('mounts files above sessions and follows the selection', async () => {
    const d = detail();
    d.workflows[0].steps[2].files = [
      {
        path: 'initiatives/familio-dessin-v2/DESIGN.md',
        draft: true,
        changed: true,
        run_id: 'r1',
        time: '2026-11-22T21:30:00Z',
      },
    ];
    d.sessions = [
      {
        workflow: 'spec',
        step: 'tech',
        kind: 'session',
        id: '0193a1b2-0000-7000-8000-0000000011ab',
        round: 1,
        state: 'closed',
      },
    ];
    GET.mockResolvedValue(ok(d));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-files')).toBeTruthy());
    const side = document.querySelector('aside.ini-side') as HTMLElement;
    const files = within(side).getByTestId('ini-files');
    const links = within(side).getByTestId('ini-links');
    expect(files.compareDocumentPosition(links) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(links.textContent).toContain('tech · session 0193…11ab · closed');
    expect(screen.getByTestId('ini-files-1-ux').getAttribute('data-selected')).toBe('true');
    fireEvent.click(screen.getByTestId('ini-step-product'));
    expect(screen.getByTestId('ini-files-1-product').getAttribute('data-selected')).toBe('true');
    expect(screen.getByTestId('ini-files-1-ux').getAttribute('data-selected')).toBeNull();
  });
});

describe('InitiativePage forced start and cancel (story 11.4)', () => {
  const parkedDetail = (over: Partial<Detail> = {}): Detail => {
    const d = detail(over);
    d.workflows[0].steps = d.workflows[0].steps.map((s) =>
      s.id === 'ux' ? { ...s, park_kind: 'conversation', park_seq: 7, run_id: 'run-s' } : s,
    );
    return d;
  };

  it('shows Start now on the next step; the modal opens and survives a poll', async () => {
    GET.mockResolvedValue(ok(parkedDetail()));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-force-plan')).toBeTruthy());
    expect(document.querySelectorAll('[data-testid^="ini-force-"]')).toHaveLength(1);
    fireEvent.click(screen.getByTestId('ini-force-plan'));
    expect(screen.getByRole('dialog', { name: 'START PLAN NOW' })).toBeTruthy();
    expect(screen.getByRole('dialog').textContent).toContain(
      'build cannot start before spec passes it',
    );
    act(() => forceTick());
    await waitFor(() => expect(initiativeCalls()).toHaveLength(2));
    expect(screen.getByRole('dialog', { name: 'START PLAN NOW' })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(POST).not.toHaveBeenCalled();
  });

  it('keeps the modal open when a poll removes the target', async () => {
    GET.mockResolvedValueOnce(ok(parkedDetail()));
    GET.mockResolvedValue(ok(detail()));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-force-plan')).toBeTruthy());
    fireEvent.click(screen.getByTestId('ini-force-plan'));
    act(() => forceTick());
    await waitFor(() => expect(screen.queryByTestId('ini-force-plan')).toBeNull());
    expect(screen.getByRole('dialog', { name: 'START PLAN NOW' })).toBeTruthy();
  });

  it('shows no Start now when the selected workflow is not the current one', async () => {
    GET.mockResolvedValue(ok(parkedDetail()));
    mount(2);
    await waitFor(() => expect(screen.getByTestId('ini-header')).toBeTruthy());
    expect(document.querySelectorAll('[data-testid^="ini-force-"]')).toHaveLength(0);
  });

  it('AC6: the header carries Cancel initiative and opens the modal', async () => {
    GET.mockResolvedValue(ok(detail()));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-cancel')).toBeTruthy());
    expect(screen.getByTestId('ini-cancel').textContent).toBe('Cancel initiative');
    fireEvent.click(screen.getByTestId('ini-cancel'));
    expect(screen.getByRole('dialog', { name: 'CANCEL INITIATIVE' })).toBeTruthy();
    fireEvent.click(screen.getByText('Keep it'));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it.each(['done', 'cancelled'] as const)('AC6: no cancel control when %s', async (status) => {
    GET.mockResolvedValue(ok(detail({ status })));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-header')).toBeTruthy());
    expect(screen.queryByTestId('ini-cancel')).toBeNull();
  });

  it('AC7: a cancelled initiative is a read-only record', async () => {
    const d = parkedDetail({
      status: 'cancelled',
      step: 'ux',
      cancelled_at: '2026-11-22T21:50:00Z',
    } as Partial<Detail>);
    GET.mockResolvedValue(ok(d));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-header')).toBeTruthy());
    const header = screen.getByTestId('ini-header');
    expect(header.textContent).toContain('CAN');
    expect(header.textContent).toContain('cancelled at ux · 21:50');
    expect(screen.queryByTestId('ini-message')).toBeNull();
    expect(screen.queryByTestId('ini-send')).toBeNull();
    expect(document.querySelectorAll('[data-testid^="ini-force-"]')).toHaveLength(0);
    expect(screen.queryByTestId('ini-cancel')).toBeNull();
  });
});

describe('InitiativePage stops (story 11.5, 2026-11-26)', () => {
  const stopTest = (id = 'ini-stop') => screen.queryByTestId(id);

  it('AC1: a merge conflict shows the banner, the conversation and a banner cancel', async () => {
    const d = detail({
      status: 'waiting for her',
      attention: 'blocked',
      current_step: 'merge',
      workflows: [
        workflow('spec', 1, {
          run_id: 'run-s',
          steps: [
            step('merge', {
              kind: 'automatic',
              park_kind: 'merge_conflict',
              conflict_files: ['planning/decision-log.md'],
              run_id: 'run-s',
              agent: 'merge agent',
              turns: [turn(1)],
            } as never),
          ],
        }),
        workflow('build', 2, { type: 'auto' }),
      ],
    } as never);
    GET.mockResolvedValue(ok(d));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-stop')).toBeTruthy());
    expect(screen.getByTestId('ini-stop').textContent).toContain(
      'merge conflict · planning/decision-log.md',
    );
    expect(screen.getByTestId('ini-conversation')).toBeTruthy();
    expect(screen.queryByTestId('ini-auto-step')).toBeNull();
    expect(screen.getByTestId('ini-message')).toBeTruthy();
    expect(
      screen
        .getAllByRole('status')
        .map((e) => e.textContent)
        .join(),
    ).toContain('your turn · nothing is pushed to main until the agent retries');
    const cancels = screen.getAllByTestId('ini-cancel');
    expect(cancels).toHaveLength(2);
    fireEvent.click(within(screen.getByTestId('ini-stop')).getByTestId('ini-cancel'));
    expect(screen.getByRole('dialog', { name: 'CANCEL INITIATIVE' })).toBeTruthy();
  });

  it('AC5: an advance banner shows with either selection and no ini-reopen', async () => {
    GET.mockResolvedValue(
      ok(detail({ status: 'waiting for her', reason: 'preflight: harness: not ready' } as never)),
    );
    mount();
    await waitFor(() => expect(stopTest()).toBeTruthy());
    expect(screen.getByTestId('ini-stop').textContent).toContain('preflight: harness: not ready');
    fireEvent.click(screen.getByTestId('ini-workflow-build'));
    expect(stopTest()).toBeTruthy();
    expect(stopTest('ini-reopen')).toBeNull();
  });

  it('AC6: the budget banner shows only with build selected', async () => {
    const d = detail({
      status: 'waiting for her',
      reason: 'no project budget',
      workflows: [
        workflow('spec', 1, { run_id: 'run-s' }),
        workflow('build', 2, { type: 'auto', run_id: null }),
      ],
    } as never);
    GET.mockResolvedValue(ok(d));
    mount(2);
    await waitFor(() => expect(stopTest()).toBeTruthy());
    expect(screen.getByTestId('ini-budget')).toBeTruthy();
    fireEvent.click(screen.getByTestId('ini-workflow-spec'));
    expect(stopTest()).toBeNull();
  });

  it('AC8: waiting for the pull request merge shows no banner', async () => {
    GET.mockResolvedValue(
      ok(detail({ status: 'running', reason: 'waiting for the pull request merge' } as never)),
    );
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-header')).toBeTruthy());
    expect(stopTest()).toBeNull();
  });

  it('AC2: Restart step through the island posts the session retry', async () => {
    POST.mockResolvedValue({ data: {} });
    const d = detail({
      status: 'waiting for her',
      attention: 'blocked',
      reason: '',
      sessions: [{ workflow: 'spec', step: 'ux', kind: 'session', state: 'open', id: 's1' }],
      workflows: [
        workflow('spec', 1, {
          steps: [
            step('ux', {
              run_id: 'run-s',
              turns: [turn(1, { status: 'failed', failure_reason: 'stalled' })],
            } as never),
          ],
        }),
        workflow('build', 2, { type: 'auto' }),
      ],
    } as never);
    GET.mockResolvedValue(ok(d));
    mount();
    await waitFor(() => expect(screen.getByTestId('ini-restart')).toBeTruthy());
    fireEvent.click(screen.getByTestId('ini-restart'));
    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith('/runs/{run_id}/session/retry', {
        params: { path: { run_id: 'run-s' } },
      }),
    );
  });
});
