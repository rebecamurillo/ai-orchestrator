/**
 * Story 2-4, CAP-7: the Run page's senior session, as pure rules (`src/lib/run/session.ts`).
 * The components that render them are `run-session-panel.test.ts`.
 */
import { describe, expect, it } from 'vitest';

import type { components } from '../../src/api/schema';
import {
  allConfirmed,
  canSend,
  canStart,
  confirmedFor,
  defaultScope,
  endBody,
  keepsFastPoll,
  logHref,
  messageBody,
  messagesRequestPath,
  offersSession,
  opensReview,
  reconcileModel,
  revertMessage,
  sessionOpen,
  sessionRequestPath,
  startBody,
  startableHarnesses,
  toggleConfirmed,
  turnState,
  type SessionOut,
  type SessionTurn,
} from '../../src/lib/run/session';

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
    attempt_id: '0198a1b2-0000-7000-8000-000000000001',
    cost_usd: null,
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

describe('offersSession and sessionOpen', () => {
  it('offers the session only where the read says one can start and none is open', () => {
    expect(offersSession(session())).toBe(true);
    expect(offersSession(session({ available: false }))).toBe(false);
    expect(offersSession(session({ active: true, available: false }))).toBe(false);
    expect(offersSession(null)).toBe(false);
  });

  it('reads an open session off the read or off the signals the server still admits', () => {
    expect(sessionOpen(session({ active: true }), ['cancel'])).toBe(true);
    expect(sessionOpen(null, ['cancel', 'session_end'])).toBe(true);
    expect(sessionOpen(session(), ['retry', 'cancel'])).toBe(false);
    expect(sessionOpen(null, [])).toBe(false);
  });
});

describe('the start form', () => {
  it('preselects the narrowest scope the stop has', () => {
    expect(defaultScope(['story', 'epic', 'run'])).toBe('story');
    expect(defaultScope(['epic', 'run'])).toBe('epic');
    expect(defaultScope(['run'])).toBe('run');
    expect(defaultScope([])).toBe('');
  });

  it('lists the enabled harnesses only, in the order served', () => {
    const harnesses = [
      { name: 'claude', enabled: true },
      { name: 'codex', enabled: false },
      { name: 'opencode', enabled: true },
    ] as components['schemas']['HarnessOut'][];
    expect(startableHarnesses(harnesses).map((h) => h.name)).toEqual(['claude', 'opencode']);
  });

  it('keeps a model only while the probe lists it', () => {
    expect(reconcileModel('opus', ['opus', 'sonnet'])).toBe('opus');
    expect(reconcileModel('opus', ['sonnet'])).toBe('');
    expect(reconcileModel('typed-name', [])).toBe('typed-name');
    expect(reconcileModel('', ['sonnet'])).toBe('');
  });

  it('starts only on a scope and a harness whose probe passed, with nothing in flight', () => {
    const ok = { ok: true, models: [], version: '1', failing_reason: null };
    const failed = { ok: false, models: [], version: '', failing_reason: 'not logged in' };
    const ready: Parameters<typeof canStart>[0] = {
      scope: 'story',
      harness: 'claude',
      probe: ok,
      probing: false,
      posting: false,
    };
    expect(canStart(ready)).toBe(true);
    expect(canStart({ ...ready, scope: '' })).toBe(false);
    expect(canStart({ ...ready, harness: '' })).toBe(false);
    expect(canStart({ ...ready, probe: null })).toBe(false);
    expect(canStart({ ...ready, probe: failed })).toBe(false);
    expect(canStart({ ...ready, probing: true })).toBe(false);
    expect(canStart({ ...ready, posting: true })).toBe(false);
  });

  it('builds the session_start body with the model only when one was chosen', () => {
    expect(startBody('epic', 'claude', 'opus')).toEqual({
      kind: 'session_start',
      payload: { scope: 'epic', harness: 'claude', model: 'opus' },
    });
    expect(startBody('run', 'codex', '')).toEqual({
      kind: 'session_start',
      payload: { scope: 'run', harness: 'codex' },
    });
  });
});

describe('the close', () => {
  it('builds session_end with the confirmed paths, or with no payload', () => {
    expect(endBody([])).toEqual({ kind: 'session_end' });
    expect(endBody(['stories.yaml', 'repos/m/AGENTS.md'])).toEqual({
      kind: 'session_end',
      payload: { confirmed_paths: ['stories.yaml', 'repos/m/AGENTS.md'] },
    });
  });

  it('opens the anchor review on a refused close when the session lists edits', () => {
    const refusal = { status: 409, title: 'Conflict', type: 'about:blank', detail: 'any text' };
    const edits = [{ kind: 'modified', path: 'stories.yaml' }] as SessionOut['anchor_edits'];
    expect(opensReview(refusal, session({ active: true, anchor_edits: edits }))).toBe(true);
    // whatever the sentence says: the list is the structured fact, the text is not parsed
    expect(
      opensReview({ ...refusal, detail: 'turn running' }, session({ anchor_edits: edits })),
    ).toBe(true);
    expect(opensReview(refusal, session({ active: true }))).toBe(false);
    expect(opensReview(refusal, null)).toBe(false);
    expect(opensReview(null, session({ active: true, anchor_edits: edits }))).toBe(false);
  });

  it('toggles a confirmation without touching the set it was given', () => {
    const none = new Set<string>();
    const one = toggleConfirmed(none, 'stories.yaml');
    expect([...one]).toEqual(['stories.yaml']);
    expect(none.size).toBe(0);
    expect([...toggleConfirmed(one, 'stories.yaml')]).toEqual([]);
  });

  it('sends only confirmations of files still listed, and closes only when all are confirmed', () => {
    const edits = [
      { kind: 'modified', path: 'stories.yaml' },
      { kind: 'added', path: 'SPEC.md' },
    ] as components['schemas']['AnchorEditOut'][];
    const confirmed = new Set(['stories.yaml', 'gone.md']);
    expect(confirmedFor(edits, confirmed)).toEqual(['stories.yaml']);
    expect(allConfirmed(edits, confirmed)).toBe(false);
    expect(allConfirmed(edits, new Set(['stories.yaml', 'SPEC.md']))).toBe(true);
    expect(allConfirmed([], new Set())).toBe(true);
  });

  it('asks the senior to restore the file, in words that name it', () => {
    expect(revertMessage('stories.yaml')).toBe(
      'Revert stories.yaml to its state before this session, then say when it is restored.',
    );
  });
});

describe('messages and turns', () => {
  it('sends trimmed text', () => {
    expect(messageBody('  fix it \n')).toEqual({ text: 'fix it' });
  });

  it('sends when the draft has text and neither a turn nor a request is running', () => {
    const open = session({ active: true });
    expect(canSend(open, 'go', false)).toBe(true);
    expect(canSend(open, '   ', false)).toBe(false);
    expect(canSend(open, 'go', true)).toBe(false);
    expect(canSend(session({ active: true, turn_running: true }), 'go', false)).toBe(false);
    expect(canSend(null, 'go', false)).toBe(false);
  });

  it('reads a turn as running, replied, without a reply file, or failed', () => {
    expect(turnState(turn({ status: 'queued', ended_at: null }))).toBe('running');
    expect(turnState(turn({ status: 'running', ended_at: null }))).toBe('running');
    expect(turnState(turn({ status: 'done', ended_at: null }))).toBe('running');
    expect(turnState(turn())).toBe('replied');
    expect(turnState(turn({ reply: '' }))).toBe('no_reply');
    expect(turnState(turn({ status: 'error', exit_code: 2 }))).toBe('failed');
  });

  it('links the attempt log through the same-origin proxy', () => {
    expect(logHref('run-1', 'att-9')).toBe('/api/runs/run-1/attempts/att-9/log');
  });

  it('names the two requests a failed fetch would show', () => {
    expect(sessionRequestPath('run-1')).toBe('/api/runs/run-1/session');
    expect(messagesRequestPath('run-1')).toBe('/api/runs/run-1/session/messages');
  });
});

describe('keepsFastPoll', () => {
  it('polls fast for a running Run or a running turn, and slow otherwise', () => {
    expect(keepsFastPoll('running', null)).toBe(true);
    expect(keepsFastPoll('needs_you', session({ active: true, turn_running: true }))).toBe(true);
    expect(keepsFastPoll('needs_you', session({ active: true }))).toBe(false);
    expect(keepsFastPoll('needs_you', null)).toBe(false);
    expect(keepsFastPoll('done', null)).toBe(false);
  });
});
