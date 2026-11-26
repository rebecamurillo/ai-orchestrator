/** Turn and conversation-step builders for the story 11.2 tests. */
import type { components } from '../../src/api/schema';
import { step, type Step } from './initiative-fixtures';

export type Turn = components['schemas']['TurnOut'];

export const turn = (n: number, over: Partial<Turn> = {}): Turn =>
  ({
    attempt_id: `a${n}-${over.round ?? 1}`,
    author: 'operator',
    defects: null,
    ended_at: `2026-11-26T21:16:00Z`,
    failure_reason: null,
    message: `message ${n}`,
    model: 'claude-opus-5-5',
    n,
    owner: null,
    reply: `reply ${n}`,
    round: 1,
    run_id: 'run-1',
    started_at: `2026-11-26T21:15:00Z`,
    status: 'done',
    ...over,
  }) as Turn;

export const convStep = (over: Partial<Step> = {}): Step =>
  step('ux', {
    status: 'waiting for her',
    token: 'RUN',
    agent: 'ux-designer',
    harness: 'claude',
    model: 'claude-opus-5-5',
    park_kind: 'conversation',
    park_reason: null,
    run_id: 'run-1',
    file: 'DESIGN.md',
    files: [],
    turns: [],
    ...over,
  } as Partial<Step>);

export const file = (path: string) => ({
  path,
  changed: true,
  draft: false,
  run_id: null,
  time: null,
});
