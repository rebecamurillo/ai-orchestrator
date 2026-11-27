/** Story 11.2: the pure helpers of lib/initiative/conversation.ts. */
import { describe, expect, it } from 'vitest';

import {
  agentAttribution,
  answeringLine,
  blockedLine,
  clockSeconds,
  closedLine,
  closingHint,
  conversationHead,
  cut80,
  isReadOnly,
  isSendKey,
  listedTurns,
  notClosedLine,
  operatorAttribution,
  queuedLine,
  queuedLines,
  readOnlyTurns,
  roundLine,
  showsComposer,
  turnTime,
  yourTurnLine,
} from '../../src/lib/initiative/conversation';
import { convStep, file, turn } from './conversation-fixtures';
import { detail, step } from './initiative-fixtures';

describe('times and attribution', () => {
  it('formats UTC times and tolerates null', () => {
    expect(turnTime('2026-11-26T21:15:00Z')).toBe('21:15');
    expect(clockSeconds('2026-11-26T21:18:04Z')).toBe('21:18:04');
    expect(turnTime(null)).toBe('');
    expect(clockSeconds(null)).toBe('');
  });

  it('attributes operator and agent parts', () => {
    const t = turn(1);
    expect(operatorAttribution(t)).toBe('You · 21:15');
    expect(operatorAttribution(turn(1, { started_at: null }))).toBe('You');
    expect(agentAttribution(t, convStep())).toBe('Agent · claude-opus-5-5 · 21:16');
    expect(agentAttribution(turn(1, { model: null }), convStep())).toBe(
      'Agent · claude-opus-5-5 · 21:16',
    );
    expect(
      agentAttribution(turn(1, { model: null, ended_at: null }), convStep({ model: null })),
    ).toBe('Agent');
  });
});

describe('head and round line', () => {
  it('composes the head, dropping null parts', () => {
    expect(conversationHead(convStep())).toBe(
      'CONVERSATION · UX · ux-designer · claude · claude-opus-5-5',
    );
    expect(conversationHead(convStep({ agent: null, harness: null, model: null }))).toBe(
      'CONVERSATION · UX',
    );
  });

  it('counts ended turns, singular and plural, and falls back to the detail round', () => {
    const d = detail({ round: 4 } as never);
    expect(roundLine(convStep({ turns: [turn(1)] }), d)).toBe('round 1 · 1 turn');
    expect(
      roundLine(
        convStep({
          turns: [turn(1), turn(2, { status: 'failed' }), turn(3, { status: 'running' })],
        }),
        d,
      ),
    ).toBe('round 1 · 2 turns');
    expect(roundLine(convStep({ turns: [] }), d)).toBe('round 4 · 0 turns');
  });
});

describe('turn lists', () => {
  const turns = [1, 2, 3, 4, 5].map((n) => turn(n));
  it('lists no queued turn and cuts the read-only list', () => {
    expect(listedTurns([turn(1), turn(2, { status: 'queued' })]).map((t) => t.n)).toEqual([1]);
    expect(readOnlyTurns(turns, false).map((t) => t.n)).toEqual([3, 4, 5]);
    expect(readOnlyTurns(turns, true)).toHaveLength(5);
  });
});

describe('mechanism lines', () => {
  it('answering and queued lines', () => {
    expect(answeringLine(turn(15, { started_at: '2026-11-26T21:18:04Z' }))).toBe(
      'agent answering turn 15 · started 21:18:04',
    );
    expect(queuedLine(turn(16, { message: 'short' }), 15)).toBe(
      'queued · waits for turn 15 to finish: "short"',
    );
    expect(cut80('x'.repeat(120))).toBe('x'.repeat(80));
    expect(queuedLine(turn(16, { message: 'y'.repeat(120) }), 15)).toContain(`"${'y'.repeat(80)}"`);
  });

  it('queuedLines wait for the running turn, else the highest lower turn', () => {
    const q = turn(16, { status: 'queued', message: 'q' });
    expect(queuedLines([turn(14), turn(15, { status: 'running' }), q])).toEqual([
      { turn: q, text: 'queued · waits for turn 15 to finish: "q"' },
    ]);
    expect(queuedLines([turn(14), q])[0].text).toContain('turn 14');
    expect(queuedLines([q])[0].text).toContain('turn 0');
  });

  it('your turn line', () => {
    const d = detail({ attention: 'your_turn', reason: '' });
    const s = convStep({ turns: [turn(14)] });
    expect(yourTurnLine(d, s, true)).toBe('your turn · turn 15');
    expect(yourTurnLine(d, convStep(), true)).toBe('your turn · turn 1');
    expect(yourTurnLine(d, s, false)).toBeNull();
    expect(yourTurnLine(detail({ attention: 'your_turn', reason: 'x' }), s, true)).toBeNull();
    expect(yourTurnLine(detail({ attention: 'answering' }), s, true)).toBeNull();
  });

  it('closed line', () => {
    const closed = convStep({ token: 'DON', files: [file('DESIGN.md'), file('EXPERIENCE.md')] });
    expect(closedLine(closed, step('tech', { status: 'running' }), 'slug')).toEqual({
      text: 'step closed · DESIGN.md, EXPERIENCE.md written · committed on spec/slug',
      next: 'tech',
    });
    expect(closedLine(closed, step('tech'), 'slug')?.next).toBeNull();
    expect(closedLine(closed, null, 'slug')?.next).toBeNull();
    expect(closedLine(convStep({ token: 'DON', files: [] }), null, 'slug')?.text).toBe(
      'step closed · committed on spec/slug',
    );
    expect(closedLine(convStep(), null, 'slug')).toBeNull();
    expect(closedLine(step('x', { kind: 'automatic', token: 'DON' }), null, 'slug')).toBeNull();
  });

  it('not closed and blocked lines', () => {
    const reason = 'step not closed · EXPERIENCE.md has status draft · the step stays open';
    const parked = convStep({ park_reason: reason });
    const blocked = detail({ attention: 'blocked', reason: 'R' });
    expect(notClosedLine(parked, true)).toBe(reason);
    expect(notClosedLine(parked, false)).toBeNull();
    expect(notClosedLine(convStep({ park_reason: 'other' }), true)).toBeNull();
    expect(notClosedLine(convStep(), true)).toBeNull();
    expect(blockedLine(blocked, convStep({ park_reason: 'other' }), true)).toBe('step blocked · R');
    expect(blockedLine(detail({ attention: 'blocked', reason: '' }), convStep(), true)).toBe(
      'step blocked',
    );
    expect(blockedLine(blocked, parked, true)).toBeNull();
    expect(blockedLine(blocked, convStep(), false)).toBeNull();
    expect(blockedLine(detail({ attention: 'your_turn' }), convStep(), true)).toBeNull();
    expect(
      blockedLine(blocked, convStep({ turns: [turn(1, { status: 'failed' })] }), true),
    ).toBeNull();
  });
});

describe('state and keys', () => {
  it('read-only and composer predicates', () => {
    expect(isReadOnly(convStep({ token: 'DON' }))).toBe(true);
    expect(isReadOnly(convStep({ token: 'SKP' }))).toBe(true);
    expect(isReadOnly(convStep())).toBe(false);
    const d = detail();
    expect(showsComposer(d, convStep(), true)).toBe(true);
    expect(showsComposer(d, convStep(), false)).toBe(false);
    expect(showsComposer(d, convStep({ park_kind: 'blocked' }), true)).toBe(false);
    expect(showsComposer(d, convStep({ run_id: null }), true)).toBe(false);
    expect(showsComposer(detail({ status: 'cancelled' }), convStep(), true)).toBe(false);
  });

  it('closing hint falls back to the declared file', () => {
    const tail = 'The step closes when the file holds its done content.';
    expect(closingHint(convStep({ files: [file('A.md'), file('B.md')] }))).toBe(
      `Say you are done in your own words; the agent confirms in one line and writes A.md, B.md. ${tail}`,
    );
    expect(closingHint(convStep({ files: [], file: 'DESIGN.md' }))).toContain('writes DESIGN.md.');
  });

  it('send key', () => {
    const k = (key: string, ctrlKey = false, metaKey = false) =>
      isSendKey({ key, ctrlKey, metaKey });
    expect(k('Enter')).toBe(false);
    expect(k('Enter', true)).toBe(true);
    expect(k('Enter', false, true)).toBe(true);
    expect(k('a', true)).toBe(false);
  });
});
