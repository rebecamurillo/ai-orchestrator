/** Story 11.5: the pure helpers of the stops (`lib/initiative/stops.ts`). */
import { describe, expect, it } from 'vitest';

import {
  defectsEyebrow,
  doneCount,
  failedTurnLine,
  gateAgent,
  gateAttribution,
  isMergeConflict,
  mergeYourTurnLine,
  ownersLine,
  stopBanner,
  stopStateLine,
  validBudget,
} from '../../src/lib/initiative/stops';
import { detail, step, workflow, type Detail, type Step } from './initiative-fixtures';

const turn = (n: number, over: Record<string, unknown> = {}) => ({
  n,
  status: 'done',
  attempt_id: `att-${n}`,
  run_id: 'run-s',
  author: 'operator',
  message: 'm',
  reply: 'r',
  round: 1,
  failure_reason: null,
  defects: null,
  owner: null,
  started_at: '2026-11-22T22:10:00Z',
  ended_at: null,
  model: null,
  ...over,
});

const session = { workflow: 'spec', step: 'ux', kind: 'session', state: 'open', id: 's1' };

function make(stepOver: Partial<Step>, over: Partial<Detail> = {}, wfOver = {}): Detail {
  return detail({
    status: 'waiting for her',
    attention: 'blocked',
    reason: '',
    sessions: [],
    workflows: [
      workflow('spec', 1, { run_id: 'run-s', steps: [step('ux', stepOver)], ...wfOver }),
      workflow('build', 2, { type: 'auto' }),
    ],
    ...over,
  } as Partial<Detail>);
}

const failedTurns = [
  ...Array.from({ length: 14 }, (_, i) => turn(i + 1)),
  turn(15, { status: 'failed', failure_reason: 'stalled: no activity for 30 min' }),
];

describe('stopBanner', () => {
  it('is null for cancelled, done, waiting for the merge and no stop', () => {
    expect(stopBanner(make({}, { status: 'cancelled', reason: 'x' }), 1)).toBeNull();
    expect(stopBanner(make({}, { status: 'done', reason: 'x' }), 1)).toBeNull();
    expect(stopBanner(make({}, { reason: 'waiting for the pull request merge' }), 1)).toBeNull();
    expect(stopBanner(make({}, { status: 'running', attention: 'your_turn' }), 1)).toBeNull();
    expect(stopBanner(make({}, { reason: 'step not closed · x' }), 1)).toBeNull();
  });

  it('merge conflict: amber, files joined, current workflow selected only', () => {
    const d = make({
      kind: 'automatic',
      park_kind: 'merge_conflict',
      conflict_files: ['a.md', 'b.md'],
    });
    const b = stopBanner(d, 1);
    expect(b?.kind).toBe('merge');
    expect(b?.tone).toBe('amber');
    expect(b?.head).toBe('merge conflict · a.md, b.md');
    expect(b?.body).toContain('resolve 2 file(s)');
    expect(b?.body).toContain('spec/familio-dessin-v2 is kept.');
    expect(stopBanner(d, 2)).toBeNull();
    expect(isMergeConflict(d.workflows[0].steps[0])).toBe(true);
  });

  it('stalled with an open session retries the Run', () => {
    const d = make(
      { turns: failedTurns, run_id: 'run-s' } as Partial<Step>,
      {
        sessions: [session],
      } as Partial<Detail>,
    );
    const b = stopBanner(d, 1);
    expect(b?.tone).toBe('red');
    expect(b?.head).toBe('stalled: no activity for 30 min');
    expect(b?.body).toBe(
      'The conversation is kept, 14 turns. Restart continues the same conversation from turn 15; no message is lost.',
    );
    expect(b?.restart).toEqual({ kind: 'retry', runId: 'run-s' });
    expect(stopBanner(d, 2)).toBeNull();
  });

  it('stalled with no open session shows no restart; a failed Run reopens', () => {
    const noSession = make({ turns: failedTurns, run_id: 'run-s' } as Partial<Step>);
    expect(stopBanner(noSession, 1)?.restart).toBeNull();
    const failedRun = make(
      { turns: [turn(1)] } as Partial<Step>,
      { status: 'failed' } as Partial<Detail>,
      { status: 'failed' },
    );
    const b = stopBanner(failedRun, 1);
    expect(b?.head).toBe('failed');
    expect(b?.restart).toEqual({ kind: 'reopen', step: 'ux', reason: 'failed' });
    const cancelled = make(
      { turns: [] },
      { status: 'failed', reason: 'Run cancelled' } as Partial<Detail>,
      { status: 'failed' },
    );
    expect(stopBanner(cancelled, 1)).toMatchObject({
      head: 'Run cancelled',
      restart: { kind: 'reopen', step: 'ux', reason: 'Run cancelled' },
    });
  });

  it('headOf falls back reason, failure reason, status word', () => {
    const withReason = make({ turns: failedTurns } as Partial<Step>, { reason: 'why' });
    expect(stopBanner(withReason, 1)?.head).toBe('why');
    const noFailureReason = make({
      turns: [turn(1, { status: 'failed' })],
    } as Partial<Step>);
    expect(stopBanner(noFailureReason, 1)?.head).toBe('needs you');
  });

  it('failed merge, gate or build Run: red, no body, no restart', () => {
    const d = make({ kind: 'automatic' }, { status: 'failed', reason: '' } as Partial<Detail>, {
      status: 'failed',
    });
    expect(stopBanner(d, 1)).toMatchObject({
      kind: 'failed',
      tone: 'red',
      head: 'failed',
      body: null,
      restart: null,
    });
    expect(stopBanner(d, 2)).toBeNull();
    const build = detail({
      status: 'failed',
      reason: 'verify failed',
      current_position: 2,
      current_step: null,
      workflows: [workflow('spec', 1), workflow('build', 2, { type: 'auto', status: 'failed' })],
    } as Partial<Detail>);
    expect(stopBanner(build, 2)?.head).toBe('verify failed');
  });

  it('missing budget names the workflow without a Run', () => {
    const base = {
      status: 'waiting for her',
      reason: 'no project budget',
      project_name: 'familio',
    } as Partial<Detail>;
    const onSpec = make({ status: 'done' }, base);
    const b = stopBanner(onSpec, 2);
    expect(b?.kind).toBe('budget');
    expect(b?.workflow).toBe('build');
    expect(b?.head).toBe('build not started: project familio has no default budget');
    expect(b?.body).toBe(
      "A Run's budget is your decision. The value is saved as the project default and the build starts on feat/familio-dessin-v2 from main.",
    );
    expect(stopBanner(onSpec, 1)).toBeNull();
    const onBuild = detail({
      ...base,
      current_position: 2,
      current_step: null,
      workflows: [
        workflow('spec', 1, { run_id: 'r1' }),
        workflow('build', 2, { type: 'auto', run_id: null }),
      ],
    } as Partial<Detail>);
    expect(stopBanner(onBuild, 2)?.workflow).toBe('build');
    const allStarted = detail({
      ...base,
      workflows: [workflow('spec', 1, { run_id: 'r1' }), workflow('build', 2, { run_id: 'r2' })],
    } as Partial<Detail>);
    expect(stopBanner(allStarted, 1)?.workflow).toBe('spec');
    const none = detail({ ...base, workflows: [] } as Partial<Detail>);
    expect(stopBanner(none, 1)).toBeNull();
  });

  it('advance blocked: reason as head, any selection', () => {
    const d = make({}, { reason: 'preflight: harness: not ready' });
    for (const position of [1, 2]) {
      expect(stopBanner(d, position)).toMatchObject({
        kind: 'advance',
        tone: 'amber',
        head: 'preflight: harness: not ready',
        body: null,
        restart: null,
      });
    }
  });
});

describe('lines', () => {
  it('failedTurnLine and doneCount', () => {
    const s = step('ux', { turns: failedTurns } as Partial<Step>);
    expect(failedTurnLine(s)).toEqual({
      text: 'turn 15 failed · stalled: no activity for 30 min · ',
      runId: 'run-s',
      attemptId: 'att-15',
    });
    expect(doneCount(s)).toBe(14);
    const bare = step('ux', { turns: [turn(1, { status: 'failed' })] } as Partial<Step>);
    expect(failedTurnLine(bare)?.text).toBe('turn 1 failed · ');
    expect(failedTurnLine(step('ux', { turns: [turn(1)] } as Partial<Step>))).toBeNull();
    expect(failedTurnLine(step('ux'))).toBeNull();
    expect(doneCount(step('ux'))).toBe(0);
  });

  it('ownersLine', () => {
    const d = detail({ round: 2, owners: ['tech', 'ux2'] } as Partial<Detail>);
    expect(ownersLine(d, step('tech'), true)).toBe('after this step closes, ux2 reopens');
    expect(ownersLine(d, step('ux2'), true)).toBe(
      'after this step closes, the gate re-runs · no other step reopens',
    );
    expect(ownersLine(d, step('tech'), false)).toBeNull();
    expect(ownersLine(d, step('other'), true)).toBeNull();
    expect(
      ownersLine(detail({ round: 1, owners: ['tech'] } as Partial<Detail>), step('tech'), true),
    ).toBeNull();
  });

  it('mergeYourTurnLine', () => {
    const s = step('merge', { park_kind: 'merge_conflict' } as Partial<Step>);
    expect(mergeYourTurnLine(s, true)).toBe(
      'your turn · nothing is pushed to main until the agent retries',
    );
    expect(mergeYourTurnLine(s, false)).toBeNull();
    expect(mergeYourTurnLine(step('ux'), true)).toBeNull();
  });

  it('defects eyebrow, gate agent and attribution', () => {
    const s = step('tech');
    expect(defectsEyebrow(turn(1, { defects: 2, owner: 'tech' }) as never, s)).toBe(
      '2 DEFECTS · OWNER TECH',
    );
    expect(defectsEyebrow(turn(1) as never, step('ux'))).toBe('DEFECTS · OWNER UX');
    const w = workflow('spec', 1, {
      steps: [step('tech'), step('gate', { kind: 'automatic', agent: 'delivery-lead' })],
    });
    expect(gateAgent(w, s)).toBe('delivery-lead');
    expect(gateAgent(workflow('spec', 1, { steps: [s] }), s)).toBeNull();
    expect(gateAttribution(turn(1) as never, 'delivery-lead')).toBe('Gate · delivery-lead · 22:10');
    expect(gateAttribution(turn(1, { started_at: null }) as never, null)).toBe('Gate');
  });

  it('stopStateLine', () => {
    expect(
      stopStateLine(
        detail({ status: 'done', pr_merged_at: '2026-11-29T08:00:00Z' } as Partial<Detail>),
      ),
    ).toBe('done · pull request merged 2026-11-29');
    expect(
      stopStateLine(
        detail({
          status: 'running',
          workflow: 'build',
          reason: 'waiting for the pull request merge',
        } as Partial<Detail>),
      ),
    ).toBe('running · build done · waiting for the pull request merge');
    expect(stopStateLine(detail())).toBeNull();
  });
});

describe('validBudget', () => {
  it.each([
    ['60', true],
    ['60.5', true],
    ['60.50', true],
    [' 7 ', true],
    ['0', false],
    ['-5', false],
    ['12.345', false],
    ['abc', false],
    ['', false],
  ])('%j → %s', (raw, ok) => expect(validBudget(raw)).toBe(ok));
});

describe('stopBanner on a cancelled spec Run (review, 2026-11-26)', () => {
  it('reopens when the workflow carries the Run status cancelled', () => {
    const d = make(
      { turns: [turn(1)] } as Partial<Step>,
      { status: 'failed', reason: 'Run cancelled' } as Partial<Detail>,
      { status: 'cancelled' },
    );
    expect(stopBanner(d, 1)).toMatchObject({
      kind: 'stalled',
      head: 'Run cancelled',
      restart: { kind: 'reopen', step: 'ux', reason: 'Run cancelled' },
    });
  });
});
