// @vitest-environment jsdom
/** Logs in words (epic 2 story 4, EXPERIENCE § 6.4): LogViewer states, drawer not_run, step page. */
import { createElement } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import LogViewer from '../../src/components/run/LogViewer';
import StepDrawer from '../../src/components/run/StepDrawer';
import StepDetail from '../../src/islands/StepDetail';
import { $stepDrawer, openStepDrawer } from '../../src/stores/step-drawer';
import { shellDrawer } from '../fixtures/step-drawer';

const LOG = '/runs/{run_id}/attempts/{attempt_id}/log';
const OK = { response: { ok: true, status: 200 } };

function logPage(page: Record<string, unknown>) {
  GET.mockImplementation(async (route: string) =>
    route === LOG
      ? { data: { eof: true, lines: [], next_cursor: 0, ...page }, ...OK }
      : { data: undefined, ...OK },
  );
}

function viewer(exitCode: number | null = null, seconds: number | null = null) {
  render(
    createElement(LogViewer, { runId: 'r1', attemptId: 'a1', isRunning: false, exitCode, seconds }),
  );
}

afterEach(() => {
  cleanup();
  GET.mockReset();
  $stepDrawer.set(null);
});

describe('LogViewer states', () => {
  it('AC1 reason-less no_output: words and download', async () => {
    logPage({ state: 'no_output', reason: null });
    viewer();
    await screen.findByText('no output · the command ran and printed nothing');
    expect(screen.getByText('download raw').getAttribute('href')).toBe(
      '/api/v1/runs/r1/attempts/a1/log?download=true',
    );
  });

  it('AC2 no_output with a reason: no download', async () => {
    logPage({ state: 'no_output', reason: 'no log was recorded for this attempt' });
    viewer();
    await screen.findByText('no output · no log was recorded for this attempt');
    expect(screen.queryByText('download raw')).toBeNull();
  });

  it('AC3 removed with removed_at', async () => {
    logPage({
      state: 'removed',
      removed_at: '2026-11-29T03:00:00Z',
      lines: ['log no longer on disk'],
    });
    viewer(1, 42);
    await screen.findByText(
      'log removed by the retention sweep on 2026-11-29 · exit 1 · 42s were recorded',
    );
    expect(screen.queryByText('log no longer on disk')).toBeNull();
    expect(screen.queryByText('download raw')).toBeNull();
    cleanup();
    viewer(null, null);
    await screen.findByText(
      'log removed by the retention sweep on 2026-11-29 · exit — · — were recorded',
    );
  });

  it('AC4 removed without removed_at', async () => {
    logPage({ state: 'removed', removed_at: null, lines: ['log no longer on disk'] });
    viewer();
    await screen.findByText('log no longer on disk');
    expect(screen.queryByText('download raw')).toBeNull();
  });

  it('AC5 text: lines and download, no words line', async () => {
    logPage({ state: 'text', lines: ['a', 'b'], next_cursor: 4 });
    const { container } = render(
      createElement(LogViewer, {
        runId: 'r1',
        attemptId: 'a1',
        isRunning: false,
        exitCode: 0,
        seconds: 1,
      }),
    );
    await screen.findByText('a');
    expect(screen.getByText('b')).toBeTruthy();
    expect(container.querySelector('.wf-log-words')).toBeNull();
    expect(screen.getByText('download raw')).toBeTruthy();
  });

  it('shows no download before the first page answers', () => {
    GET.mockReturnValue(new Promise(() => {}));
    viewer();
    expect(screen.queryByText('download raw')).toBeNull();
  });
});

describe('StepDrawer log', () => {
  it('AC6 not_run reads not run · reason and mounts no viewer', async () => {
    GET.mockResolvedValue({
      data: shellDrawer({
        log: {
          state: 'not_run',
          attempt_id: null,
          reason: 'skipped · no command',
          removed_at: null,
        },
      }),
    });
    openStepDrawer(13, 1, 'x');
    render(createElement(StepDrawer, { runId: 'r1' }));
    await screen.findByText('not run · skipped · no command');
    expect(screen.getByTestId('wf-step-drawer-log').querySelector('.wf-log-viewer')).toBeNull();
  });
});

describe('StepDetail log', () => {
  it('AC7 shows download raw when the log exists', async () => {
    const detail = {
      seq: 1,
      path: 'epics[0].build',
      label: 'build',
      kind: 'shell',
      gate: 'deterministic',
      status: 'done',
      token: 'DON',
      reason: null,
      with_resolved: {},
      attempts: [
        {
          id: 'att-1',
          n: 1,
          status: 'done',
          exit_code: 0,
          seconds: 3,
          session_id: null,
          result: null,
        },
      ],
    };
    GET.mockImplementation(async (route: string) => {
      if (route === '/runs/{run_id}/steps/{step_path}') return { data: detail, ...OK };
      if (route === LOG)
        return { data: { eof: true, lines: ['x'], next_cursor: 2, state: 'text' }, ...OK };
      return { data: undefined, ...OK };
    });
    render(createElement(StepDetail, { runId: 'r1', dotPath: 'epics.0.build' }));
    await screen.findByText('download raw');
  });
});
