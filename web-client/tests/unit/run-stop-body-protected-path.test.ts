/**
 * `StopBody.tsx`'s protected-path body (6.6, FR-31, AD-17, UX-DR10): the file list with each
 * file's mark and diff link, the accept line, *Accept changes* — and the plain *Continue*
 * button standing aside, because on this one stop `continue` **is** the Accept and carries a
 * payload a button cannot hold.
 *
 * A new file rather than a case added to `run-stop-body-skip.test.ts` /
 * `run-stop-body-skip-epic.test.ts`, which are frozen and already render a `protected_path`
 * stop: neither lists `continue` in `admitted_signals`, so both keep asserting exactly what
 * they always did. That the two skips still render here is asserted below all the same.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import StopBody from '../../src/components/run/StopBody';
import type {
  GateRecordOut,
  RunDetailOut,
  SignalKind,
  StepRowOut,
  Token,
} from '../../src/lib/run/detail';

const PARK_ROW = 'epics[0].stories[0].build';
const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939c2';
const ADMITTED = ['continue', 'retry', 'skip_story', 'skip_epic', 'cancel'] as SignalKind[];
const HITS = [
  { path: 'tests/a.py', kind: 'modified' },
  { path: 'AGENTS.md', kind: 'added' },
];

function step(over: Partial<StepRowOut> = {}): StepRowOut {
  return {
    seq: 1,
    path: PARK_ROW,
    label: 'verify',
    kind: 'shell',
    gate: 'deterministic',
    status: 'error',
    token: 'ERR',
    reason: 'exit 1',
    attempts: 1,
    latest: null,
    cost_usd: '0',
    ...over,
  } as StepRowOut;
}

function gate(over: Partial<GateRecordOut> = {}): GateRecordOut {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    at: '2026-09-09T10:00:00Z',
    path: null,
    event: 'blocked',
    actor: 'machine',
    text: '',
    attempt_n: null,
    ...over,
  };
}

function base(): RunDetailOut {
  return {
    run: {
      id: '1',
      status: 'needs_you',
      admitted_signals: [],
      branch: 'epics/1',
      budget_usd: '15',
      compare_urls: [],
      created_at: '2026-09-07T09:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: 'p1',
      repository: 'r1',
      spend_usd: '0',
      template: 'initiative',
      terminal_session: false,
      version: 1,
      worktree_path: null,
      worktrees: [],
      accepted_paths: [],
    },
    header: {
      meta: {
        project: 'demo',
        repository: 'demo-repo',
        base_branch: 'main',
        folder: 'specs/gates',
        template: 'initiative',
        version: 1,
        harness: 'fake',
        started_at: null,
        worktree_path: null,
      },
    },
    alert: null,
    steps: [step()],
    stories: [{ epic_index: 0, story_id: '2', state: 'current', cost_usd: '0' }],
    cost: {
      spent_usd: '0',
      budget_usd: '15',
      tokens_in: 0,
      tokens_out: 0,
      wall_clock_seconds: 0,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: [],
    summary: null,
  } as unknown as RunDetailOut;
}

function stopped(admitted: SignalKind[] = ADMITTED, payload: unknown = { hits: HITS }): string {
  const detail: RunDetailOut = {
    ...base(),
    alert: {
      token: 'BLK',
      reason: 'protected path modified: tests/a.py, AGENTS.md',
      park_kind: 'protected_path',
      payload,
    },
    gate_record: [gate({ event: 'protected_path', path: PARK_ROW })],
    admitted_signals: admitted,
  } as unknown as RunDetailOut;
  return renderToStaticMarkup(
    createElement(StopBody, {
      detail,
      token: 'BLK' as Token,
      onSignal: () => {},
      onCancelClick: () => {},
      posting: null,
      error: null,
      runId: RUN_ID,
    }),
  );
}

describe('StopBody . protected_path', () => {
  it('shows the reason verbatim, naming the files that stopped the Run', () => {
    expect(stopped()).toContain('protected path modified: tests/a.py, AGENTS.md');
  });

  it('lists each file the park recorded', () => {
    const html = stopped();

    expect(html).toContain('data-testid="wf-accept-file-tests/a.py"');
    expect(html).toContain('data-testid="wf-accept-file-AGENTS.md"');
  });

  it('marks a modified file and an added one differently', () => {
    const html = stopped();

    expect(html).toContain('~');
    expect(html).toContain('+');
  });

  it('links each file to its own unified diff', () => {
    const html = stopped();

    expect(html).toContain(`/api/runs/${RUN_ID}/files?path=tests%2Fa.py&amp;diff=1`);
    expect(html).toContain(`/api/runs/${RUN_ID}/files?path=AGENTS.md&amp;diff=1`);
  });

  it('states what accepting does before the button that does it', () => {
    const html = stopped();

    expect(html).toContain('data-testid="wf-accept-line"');
    expect(html).toContain('the check resumes on the same tree and the files ship with the story');
    expect(html).toContain('data-testid="wf-accept"');
    expect(html).toContain('Accept changes');
  });

  it('drops the plain Continue button, since the Accept is that signal here', () => {
    expect(stopped()).not.toContain('data-testid="wf-signal-continue"');
  });

  it('keeps every other action this stop already offered', () => {
    const html = stopped();

    expect(html).toContain('data-testid="wf-signal-retry"');
    expect(html).toContain('data-testid="wf-signal-skip_story"');
    expect(html).toContain('data-testid="wf-signal-skip_epic"');
    expect(html).toContain('data-testid="wf-cancel"');
  });

  it('keeps the plain Continue button when the park recorded no files to accept', () => {
    const html = stopped(ADMITTED, { hits: [] });

    expect(html).not.toContain('data-testid="wf-accept-files"');
    expect(html).toContain('data-testid="wf-signal-continue"');
  });

  it('renders a response that predates the payload field without throwing', () => {
    const detail = {
      ...base(),
      alert: { token: 'BLK', reason: 'protected path modified', park_kind: 'protected_path' },
      gate_record: [gate({ event: 'protected_path', path: PARK_ROW })],
      admitted_signals: ADMITTED,
    } as unknown as RunDetailOut;

    const html = renderToStaticMarkup(
      createElement(StopBody, {
        detail,
        token: 'BLK' as Token,
        onSignal: () => {},
        onCancelClick: () => {},
        posting: null,
        error: null,
        runId: RUN_ID,
      }),
    );

    expect(html).toContain('data-testid="wf-stop-protected_path"');
    expect(html).not.toContain('data-testid="wf-accept-files"');
    expect(html).toContain('data-testid="wf-signal-continue"');
  });

  it('renders no accept box when the server does not admit continue', () => {
    const html = stopped(['retry', 'cancel'] as SignalKind[]);

    expect(html).not.toContain('data-testid="wf-accept-files"');
  });

  it('never renders raw markup from a path, whatever the payload held', () => {
    const html = stopped(ADMITTED, { hits: [{ path: '<img src=x>', kind: 'added' }] });

    expect(html).not.toContain('<img src=x>');
    expect(html).toContain('&lt;img src=x&gt;');
  });
});
