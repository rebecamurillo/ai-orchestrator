// @vitest-environment jsdom
/**
 * The step drawer on the Run page (epic 2 story 2, EXPERIENCE § 6.2): openers, the drawer read,
 * focus, the run-order reopen and the shared selection mark.
 */
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET, logProps } = vi.hoisted(() => ({ GET: vi.fn(), logProps: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));
vi.mock('../../src/components/run/LogViewer', () => ({
  default: (p: Record<string, unknown>) => {
    logProps(p);
    return createElement('div', { 'data-testid': 'log-stub' });
  },
}));

import { AgentCard } from '../../src/components/run/diagram/nodes';
import StepDrawer from '../../src/components/run/StepDrawer';
import StepsTable from '../../src/components/run/StepsTable';
import { buildHierarchy } from '../../src/lib/diagram/run-tree';
import { $originTarget } from '../../src/stores/metric-ui';
import { $stepDrawer, openStepDrawer } from '../../src/stores/step-drawer';
import { agentDrawer } from '../fixtures/step-drawer';
import { step, twoEpicGraph, twoEpicSteps } from '../fixtures/run-graph';

const BUILD = 'epics[1].stories[0].build';

function card(attemptN: number | undefined, seq = 13) {
  const graph = twoEpicGraph({ seq, attempt_n: attemptN } as never);
  const built = buildHierarchy(graph, twoEpicSteps(), new Set(['epics[1]', 'epics[1].stories[0]']));
  return built.nodes.find((n) => n.id === BUILD)!;
}

function table(rows: { seq: number; latest: { n: number } | null }[]) {
  const steps = rows.map((r, i) =>
    step(`epics[0].s${i}`, { seq: r.seq, latest: r.latest as never }),
  );
  return createElement(StepsTable, {
    detail: { steps, run: {}, header: {} } as never,
    runId: 'r1',
  });
}

beforeEach(() => {
  GET.mockResolvedValue({ data: agentDrawer() });
});
afterEach(() => {
  cleanup();
  GET.mockReset();
  logProps.mockReset();
  $stepDrawer.set(null);
  $originTarget.set(null);
});

describe('openers', () => {
  it('Open step is a button that opens the drawer on (seq, attempt_n)', () => {
    const { container } = render(createElement(AgentCard, { node: card(2), runId: 'r1' }));
    const cta = screen.getByTestId(`wf-diagram-open-${'epics.1.stories.0.build'}`);
    expect(cta.tagName).toBe('BUTTON');
    expect(cta.getAttribute('type')).toBe('button');
    expect(cta.className).toBe('wf-node-cta nodrag');
    expect(container.querySelector('a')).toBeNull();
    fireEvent.click(cta);
    expect($stepDrawer.get()).toEqual({ seq: 13, n: 2, openerId: cta.id });
    expect(cta.id).not.toBe('');
  });

  it('opens on n = 0 without an attempt_n', () => {
    render(createElement(AgentCard, { node: card(undefined), runId: 'r1' }));
    fireEvent.click(screen.getByTestId('wf-diagram-open-epics.1.stories.0.build'));
    expect($stepDrawer.get()?.n).toBe(0);
  });

  it('the Steps-table path is a button on (seq, latest.n), n = 0 without a latest', () => {
    const { container } = render(
      table([
        { seq: 13, latest: { n: 2 } },
        { seq: 14, latest: null },
      ]),
    );
    expect(container.querySelector('a')).toBeNull();
    const first = screen.getByText('epics[0].s0');
    expect(first.tagName).toBe('BUTTON');
    fireEvent.click(first);
    expect($stepDrawer.get()).toEqual({ seq: 13, n: 2, openerId: first.id });
    fireEvent.click(screen.getByText('epics[0].s1'));
    expect($stepDrawer.get()?.seq).toBe(14);
    expect($stepDrawer.get()?.n).toBe(0);
  });
});

describe('StepDrawer', () => {
  it('renders nothing and fetches nothing while closed', () => {
    const { container } = render(createElement(StepDrawer, { runId: 'r1' }));
    expect(container.innerHTML).toBe('');
    expect(GET).not.toHaveBeenCalled();
  });

  it('reads the drawer and renders the sections in order', async () => {
    openStepDrawer(13, 2, 'x');
    render(createElement(StepDrawer, { runId: 'r1' }));
    await screen.findByText('RUN ORDER · epics[0].stories[0]');
    expect(GET).toHaveBeenCalledWith('/runs/{run_id}/steps/{seq}/attempts/{n}/drawer', {
      params: { path: { run_id: 'r1', seq: 13, n: 2 } },
    });
    const panel = screen.getByTestId('wf-step-drawer');
    const order = ['wf-step-drawer-order', 'wf-step-drawer-log', 'FILES READ', 'FILES WRITTEN'];
    const text = panel.innerHTML;
    const at = [
      text.indexOf('data-testid="wf-step-drawer-order"'),
      text.indexOf('data-testid="wf-step-drawer-log"'),
      text.indexOf('FILES READ'),
      text.indexOf('FILES WRITTEN'),
    ];
    expect(order).toHaveLength(4);
    expect(at.every((v) => v > 0)).toBe(true);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
    expect(text.indexOf('>build<')).toBeLessThan(at[0]!);
    expect(screen.getByText('LOG · ATTEMPT 2')).toBeTruthy();
    expect(logProps).toHaveBeenCalledWith(
      expect.objectContaining({
        runId: 'r1',
        attemptId: 'att-2',
        logPath: 'att-2',
        isRunning: true,
      }),
    );
    expect(screen.getByText('src/a.ts +3 −1')).toBeTruthy();
    expect(screen.getByTestId('wf-step-drawer-full').getAttribute('href')).toBe(
      '/workflows/r1/steps/epics.0.stories.0.build',
    );
  });

  it('mounts no log viewer without an attempt id', async () => {
    GET.mockResolvedValue({
      data: agentDrawer({
        log: { attempt_id: null, reason: null, removed_at: null, state: 'not_run' },
      }),
    });
    openStepDrawer(13, 0, 'x');
    render(createElement(StepDrawer, { runId: 'r1' }));
    await screen.findByText('LOG · ATTEMPT 2');
    expect(screen.queryByTestId('log-stub')).toBeNull();
  });

  it('omits the run order when none is sent', async () => {
    GET.mockResolvedValue({ data: agentDrawer({ run_order: null }) });
    openStepDrawer(13, 2, 'x');
    render(createElement(StepDrawer, { runId: 'r1' }));
    await screen.findByText('LOG · ATTEMPT 2');
    expect(screen.queryByTestId('wf-step-drawer-order')).toBeNull();
  });

  it('names the request on a failed read', async () => {
    GET.mockResolvedValue({ error: { status: 500 } });
    openStepDrawer(13, 2, 'x');
    render(createElement(StepDrawer, { runId: 'r1' }));
    await screen.findByText('could not read /runs/r1/steps/13/attempts/2/drawer');
  });

  it('focuses the heading on open; Escape and close return focus to the opener', async () => {
    const opener = document.createElement('button');
    opener.id = 'opener';
    document.body.append(opener);
    openStepDrawer(13, 2, 'opener');
    render(createElement(StepDrawer, { runId: 'r1' }));
    await screen.findByText('RUN ORDER · epics[0].stories[0]');
    expect(document.activeElement?.id).toBe('wf-step-drawer-heading');

    fireEvent.keyDown(document, { key: 'Escape' });
    expect($stepDrawer.get()).toBeNull();
    expect(document.activeElement).toBe(opener);

    openStepDrawer(13, 2, 'opener');
    await screen.findByText('RUN ORDER · epics[0].stories[0]');
    fireEvent.click(screen.getByText('close'));
    expect($stepDrawer.get()).toBeNull();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });

  it('falls back to the steps heading when the opener is gone', async () => {
    const heading = document.createElement('button');
    heading.id = 'wf-steps-heading';
    document.body.append(heading);
    openStepDrawer(13, 2, 'gone');
    render(createElement(StepDrawer, { runId: 'r1' }));
    await screen.findByText('RUN ORDER · epics[0].stories[0]');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(document.activeElement).toBe(heading);
    heading.remove();
  });

  it('ignores other keys and stops listening once closed', async () => {
    openStepDrawer(13, 2, 'x');
    render(createElement(StepDrawer, { runId: 'r1' }));
    await screen.findByText('RUN ORDER · epics[0].stories[0]');
    fireEvent.keyDown(document, { key: 'a' });
    expect($stepDrawer.get()).not.toBeNull();
  });

  it('a run-order row reopens on that seq with n = 0 and the original opener', async () => {
    openStepDrawer(13, 2, 'orig');
    render(createElement(StepDrawer, { runId: 'r1' }));
    await screen.findByText('RUN ORDER · epics[0].stories[0]');
    const order = screen.getByTestId('wf-step-drawer-order');
    expect(order.querySelector('[aria-current="step"]')?.textContent).toContain('build');
    fireEvent.click(screen.getByText('verify'));
    expect($stepDrawer.get()).toEqual({ seq: 14, n: 0, openerId: 'orig' });
    await waitFor(() =>
      expect(GET).toHaveBeenLastCalledWith('/runs/{run_id}/steps/{seq}/attempts/{n}/drawer', {
        params: { path: { run_id: 'r1', seq: 14, n: 0 } },
      }),
    );
  });
});

describe('StepDrawer review (epic 2 story 2, 2026-11-23)', () => {
  it('shows no line of the previous step while the next read is in flight', async () => {
    openStepDrawer(13, 2, 'x');
    render(createElement(StepDrawer, { runId: 'r1' }));
    await screen.findByText('RUN ORDER · epics[0].stories[0]');
    let resolve: (v: unknown) => void = () => {};
    GET.mockReturnValueOnce(new Promise((r) => (resolve = r)));
    act(() => openStepDrawer(14, 0, 'x'));
    expect(screen.queryByText('RUN ORDER · epics[0].stories[0]')).toBeNull();
    expect(screen.queryByTestId('wf-step-drawer-full')).toBeNull();
    await act(async () => resolve({ data: agentDrawer() }));
    await screen.findByText('RUN ORDER · epics[0].stories[0]');
  });

  it('drops a read that lands after close', async () => {
    let resolve: (v: unknown) => void = () => {};
    GET.mockReturnValueOnce(new Promise((r) => (resolve = r)));
    openStepDrawer(13, 2, 'x');
    render(createElement(StepDrawer, { runId: 'r1' }));
    fireEvent.click(screen.getByText('close'));
    await act(async () => resolve({ data: agentDrawer() }));
    GET.mockReturnValueOnce(new Promise(() => {}));
    act(() => openStepDrawer(13, 2, 'x'));
    expect(screen.queryByTestId('wf-step-drawer-order')).toBeNull();
  });

  it('yields an Escape to an open origin drawer, then closes on the next', async () => {
    openStepDrawer(13, 2, 'x');
    render(createElement(StepDrawer, { runId: 'r1' }));
    await screen.findByText('RUN ORDER · epics[0].stories[0]');
    act(() => $originTarget.set({} as never));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect($stepDrawer.get()).not.toBeNull();
    act(() => $originTarget.set(null));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect($stepDrawer.get()).toBeNull();
  });
});

describe('selection mark', () => {
  it('marks the card and row of the open seq and moves with it', () => {
    openStepDrawer(13, 0, 'x');
    const view = render(
      createElement('div', null, [
        createElement(AgentCard, { key: 'c', node: card(2), runId: 'r1' }),
        createElement(
          'div',
          { key: 't' },
          table([
            { seq: 13, latest: null },
            { seq: 14, latest: null },
          ]),
        ),
      ]),
    );
    const root = view.container.querySelector('.wf-node')!;
    const rows = () => [...view.container.querySelectorAll('tbody tr')];
    expect(root.classList.contains('wf-node-selected')).toBe(true);
    expect(rows().map((r) => r.classList.contains('wf-step-selected'))).toEqual([true, false]);
    act(() => openStepDrawer(14, 0, 'x'));
    expect(root.classList.contains('wf-node-selected')).toBe(false);
    expect(rows().map((r) => r.classList.contains('wf-step-selected'))).toEqual([false, true]);
    act(() => $stepDrawer.set(null));
    expect(rows().some((r) => r.classList.contains('wf-step-selected'))).toBe(false);
  });
});
