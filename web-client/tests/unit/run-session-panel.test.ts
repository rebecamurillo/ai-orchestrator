/**
 * Story 2-4, CAP-7: the senior session's components (`SessionPanel`, `SessionStart`,
 * `SessionTurns`, `SessionAnchors`) in their closed and open renders, and `StopBody` under
 * the server's lock. `vitest.config.ts` runs in `environment: 'node'`, so what is asserted is
 * the static markup; the clicks and the posts are `run-detail-session.spec.ts`.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import SessionAnchors from '../../src/components/run/SessionAnchors';
import SessionPanel from '../../src/components/run/SessionPanel';
import SessionStart from '../../src/components/run/SessionStart';
import SessionTurns from '../../src/components/run/SessionTurns';
import StopBody from '../../src/components/run/StopBody';
import type { RunDetailOut, SignalKind } from '../../src/lib/run/detail';
import type { SessionOut, SessionTurn } from '../../src/lib/run/session';

function session(over: Partial<SessionOut> = {}): SessionOut {
  return {
    active: false,
    available: true,
    anchor_edits: [],
    harness: null,
    model: null,
    scope: null,
    scopes: ['story', 'epic', 'run'],
    turn_running: false,
    turns: [],
    ...over,
  };
}

function turn(over: Partial<SessionTurn> = {}): SessionTurn {
  return {
    attempt_id: 'att-1',
    cost_usd: '0.40',
    ended_at: '2026-11-02T10:00:00Z',
    exit_code: 0,
    message: 'look at the failing test',
    reply: 'it asserts the old mapping',
    started_at: '2026-11-02T09:59:00Z',
    status: 'done',
    turn: 1,
    ...over,
  };
}

const noop = async () => null;

function panel(
  s: SessionOut | null,
  admitted: SignalKind[] = ['retry', 'cancel'],
  sending = false,
): string {
  return renderToStaticMarkup(
    createElement(SessionPanel, {
      runId: 'run-1',
      session: s,
      admitted,
      posting: null,
      sending,
      onStart: noop,
      onEnd: noop,
      onMessage: noop,
    }),
  );
}

describe('SessionPanel', () => {
  it('offers the session where the read says a start would pass', () => {
    const html = panel(session());
    expect(html).toContain('data-testid="wf-session-offer"');
    expect(html).toContain('Senior session');
    expect(html).not.toContain('wf-session-start');
  });

  it('offers nothing where no session can start, and before the read has landed', () => {
    expect(panel(session({ available: false }))).toBe('');
    expect(panel(null)).toBe('');
  });

  it('states the lock and the conversation while a session is open', () => {
    const html = panel(session({ active: true, available: false, turns: [turn()] }), [
      'cancel',
      'session_end',
    ]);
    expect(html).toContain('data-testid="wf-session"');
    expect(html).toContain('senior session open');
    expect(html).toContain('Cancel run stays available');
    expect(html).toContain('look at the failing test');
    expect(html).toContain('it asserts the old mapping');
    expect(html).toContain('data-testid="wf-session-close"');
    expect(html).not.toContain('wf-session-offer');
  });

  it('disables the message box and names the turn while one runs', () => {
    const running = turn({ status: 'running', ended_at: null, reply: '', turn: 2 });
    const html = panel(
      session({ active: true, available: false, turn_running: true, turns: [turn(), running] }),
      ['cancel', 'session_end'],
    );
    expect(html).toMatch(/<textarea[^>]*data-testid="wf-session-message"[^>]*disabled=""/);
    expect(html).toMatch(/<button[^>]*data-testid="wf-session-send"[^>]*disabled=""/);
    expect(html).toContain('turn 2 is running; the message box is disabled until it ends');
    expect(html).toMatch(/<button[^>]*data-testid="wf-session-close"[^>]*disabled=""/);
  });

  it('enables the box when no turn runs, and leaves Send off until there is text', () => {
    const html = panel(session({ active: true, available: false, turns: [turn()] }), [
      'cancel',
      'session_end',
    ]);
    expect(html).not.toMatch(/<textarea[^>]*data-testid="wf-session-message"[^>]*disabled=""/);
    expect(html).toMatch(/<button[^>]*data-testid="wf-session-send"[^>]*disabled=""/);
    expect(html).not.toMatch(/<button[^>]*data-testid="wf-session-close"[^>]*disabled=""/);
  });

  it('shows a close even when the read failed but the server admits it', () => {
    const html = panel(null, ['cancel', 'session_end']);
    expect(html).toContain('data-testid="wf-session-close"');
    expect(html).toMatch(/<textarea[^>]*data-testid="wf-session-message"[^>]*disabled=""/);
  });
});

describe('SessionStart', () => {
  const harnesses = [
    { name: 'claude', enabled: true, models: [] },
    { name: 'codex', enabled: true, models: [] },
  ] as unknown as Parameters<typeof SessionStart>[0]['harnesses'];

  function start(over: Record<string, unknown> = {}): string {
    return renderToStaticMarkup(
      createElement(SessionStart, {
        scopes: ['story', 'epic', 'run'],
        scope: 'story',
        harnesses,
        harness: '',
        probe: null,
        probing: false,
        model: '',
        posting: false,
        onScope: () => {},
        onHarness: () => {},
        onModel: () => {},
        onStart: () => {},
        onDismiss: () => {},
        ...over,
      } as Parameters<typeof SessionStart>[0]),
    );
  }

  it('lists the scopes the stop has and the harnesses served', () => {
    const html = start();
    expect(html).toContain('value="story"');
    expect(html).toContain('value="epic"');
    expect(html).toContain('value="run"');
    expect(html).toContain('value="claude"');
    expect(html).toContain('value="codex"');
    expect(html).toMatch(/<button[^>]*data-testid="wf-session-start"[^>]*disabled=""/);
  });

  it('offers the probed models in the New Workflow form’s model select', () => {
    const html = start({
      harness: 'claude',
      probe: { ok: true, models: ['opus', 'sonnet'], version: '1', failing_reason: null },
    });
    expect(html).toMatch(/<select[^>]*data-testid="wf-session-model"/);
    expect(html).toContain('>opus<');
    expect(html).toContain('>sonnet<');
    expect(html).toContain('harness default');
    expect(html).not.toMatch(/<button[^>]*data-testid="wf-session-start"[^>]*disabled=""/);
  });

  it('takes a typed model name when the harness lists none', () => {
    const html = start({
      harness: 'claude',
      probe: { ok: true, models: [], version: '1', failing_reason: null },
    });
    expect(html).toMatch(/<input[^>]*data-testid="wf-session-model"/);
  });

  it('prints the failing reason and keeps Start off when the probe fails', () => {
    const html = start({
      harness: 'claude',
      probe: { ok: false, models: [], version: '', failing_reason: 'claude is not logged in' },
    });
    expect(html).toContain('claude is not logged in');
    expect(html).toMatch(/<button[^>]*data-testid="wf-session-start"[^>]*disabled=""/);
  });

  it('says so when no harness is enabled, and while the list loads', () => {
    expect(start({ harnesses: [] })).toContain('no harness is enabled');
    expect(start({ harnesses: null })).not.toContain('no harness is enabled');
  });
});

describe('SessionTurns', () => {
  function turns(list: SessionTurn[]): string {
    return renderToStaticMarkup(createElement(SessionTurns, { runId: 'run-1', turns: list }));
  }

  it('shows each turn in order with its message and reply', () => {
    const html = turns([
      turn(),
      turn({ attempt_id: 'att-2', turn: 2, message: 'now the fix', reply: 'done, one line' }),
    ]);
    expect(html.indexOf('look at the failing test')).toBeLessThan(html.indexOf('now the fix'));
    expect(html).toContain('done, one line');
    expect(html).toContain('data-testid="wf-session-turn-2"');
  });

  it('renders message text as text, never as markup', () => {
    expect(turns([turn({ message: '<img src=x onerror=alert(1)>' })])).not.toContain('<img');
  });

  it('reads no reply file beside the attempt log when a finished turn left none', () => {
    const html = turns([turn({ reply: '' })]);
    expect(html).toContain('no reply file');
    expect(html).toContain('href="/api/runs/run-1/attempts/att-1/log"');
  });

  it('states a running turn and a failed one', () => {
    expect(turns([turn({ status: 'running', ended_at: null, reply: '' })])).toContain(
      'data-testid="wf-session-running"',
    );
    const failed = turns([turn({ status: 'error', exit_code: 2, reply: '' })]);
    expect(failed).toContain('turn ended in error · exit 2');
  });

  it('renders nothing before the first message', () => {
    expect(turns([])).toBe('');
  });
});

describe('SessionAnchors', () => {
  const edits = [
    { kind: 'modified', path: 'stories.yaml' },
    { kind: 'added', path: 'repos/m/AGENTS.md' },
  ] as SessionOut['anchor_edits'];

  function anchors(confirmed: string[], turnRunning = false): string {
    return renderToStaticMarkup(
      createElement(SessionAnchors, {
        edits,
        confirmed: new Set(confirmed),
        turnRunning,
        posting: false,
        onToggle: () => {},
        onRevert: () => {},
        onClose: () => {},
      }),
    );
  }

  it('lists each edit with its kind, a Confirm and a Revert', () => {
    const html = anchors([]);
    expect(html).toContain('stories.yaml');
    expect(html).toContain('modified');
    expect(html).toContain('repos/m/AGENTS.md');
    expect(html).toContain('added');
    expect(html).toContain('data-testid="wf-session-confirm-stories.yaml"');
    expect(html).toContain('data-testid="wf-session-revert-stories.yaml"');
    expect(html).toMatch(/<button[^>]*data-testid="wf-session-close-confirmed"[^>]*disabled=""/);
  });

  it('marks a confirmed file and closes only when every file is confirmed', () => {
    const some = anchors(['stories.yaml']);
    expect(some).toMatch(/data-testid="wf-session-confirm-stories.yaml"[^>]*aria-pressed="true"/);
    expect(some).toMatch(/<button[^>]*data-testid="wf-session-close-confirmed"[^>]*disabled=""/);
    const all = anchors(['stories.yaml', 'repos/m/AGENTS.md']);
    expect(all).not.toMatch(/<button[^>]*data-testid="wf-session-close-confirmed"[^>]*disabled=""/);
  });

  it('holds confirm and revert while a turn runs', () => {
    const html = anchors(['stories.yaml', 'repos/m/AGENTS.md'], true);
    expect(html).toMatch(
      /<button[^>]*data-testid="wf-session-revert-stories.yaml"[^>]*disabled=""/,
    );
    expect(html).toMatch(/<button[^>]*data-testid="wf-session-close-confirmed"[^>]*disabled=""/);
    expect(html).toContain('a turn is running');
  });

  it('says so when every edit has been reverted', () => {
    const html = renderToStaticMarkup(
      createElement(SessionAnchors, {
        edits: [],
        confirmed: new Set<string>(),
        turnRunning: false,
        posting: false,
        onToggle: () => {},
        onRevert: () => {},
        onClose: () => {},
      }),
    );
    expect(html).toContain('no anchor edit remains');
    expect(html).not.toMatch(
      /<button[^>]*data-testid="wf-session-close-confirmed"[^>]*disabled=""/,
    );
  });
});

describe('the stop under the server’s lock', () => {
  it('renders no Retry, Continue or Answer while only cancel and session_end are admitted', () => {
    const detail = {
      run: { id: '1', status: 'needs_you', branch: 'epics/1', park_seq: 2 },
      alert: { token: 'BLK', reason: 'q?', park_kind: 'blocked', row_kind: 'agent' },
      steps: [],
      stories: [],
      gate_record: [],
      admitted_signals: ['cancel', 'session_end'],
      cost: { budget_usd: '15', spent_usd: '0' },
      summary: null,
    } as unknown as RunDetailOut;
    const html = renderToStaticMarkup(
      createElement(StopBody, {
        detail,
        token: 'BLK',
        onSignal: () => {},
        onCancelClick: () => {},
        posting: null,
        error: null,
      }),
    );
    expect(html).toContain('data-testid="wf-cancel"');
    expect(html).not.toContain('wf-signal-retry');
    expect(html).not.toContain('wf-signal-continue');
    expect(html).not.toContain('wf-signal-answer');
    expect(html).not.toContain('wf-answer');
    expect(html).not.toContain('wf-signal-skip');
  });
});
