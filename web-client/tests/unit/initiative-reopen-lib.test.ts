/** Story 11.6: the pure helpers of the reopen control (`lib/initiative/reopen.ts`). */
import { describe, expect, it } from 'vitest';

import {
  freshBranchLine,
  KEEP_LABEL,
  latestRun,
  liveRun,
  reopenLabel,
  reopenMechanism,
  reopenPlacement,
  reopenQuestion,
  reopenReason,
  reopenRunId,
  reopenSteps,
  REOPEN_HEAD,
  specWorkflow,
} from '../../src/lib/initiative/reopen';
import { detail, step, workflow, type Detail, type Step } from './initiative-fixtures';

const run = (id: string, status: string, created_at: string) => ({ id, status, created_at });
const RUN_B = '0193e5f6-0000-7000-8000-00000000bb02';

function make(over: Partial<Detail> = {}, runs: unknown[] | null = null): Detail {
  return detail({
    status: 'waiting for her',
    reason: 'verify failed: make test exited 2',
    current_position: 2,
    round: 1,
    runs: runs ?? [
      run('run-s', 'done', '2026-11-20T10:00:00Z'),
      run('run-b', 'needs_you', '2026-11-22T10:00:00Z'),
    ],
    workflows: [
      workflow('spec', 1, {
        steps: [
          step('intake', { number: '1.1', agent: 'intake-router' }),
          step('product', { number: '1.2', agent: 'product-lead' }),
        ],
      }),
      workflow('build', 2, { type: 'auto', run_id: 'run-b' }),
    ],
    ...over,
  } as unknown as Partial<Detail>);
}

describe('latestRun and liveRun', () => {
  it('none, one, several', () => {
    expect(latestRun(make({}, []))).toBeNull();
    expect(liveRun(make({}, []))).toBeNull();
    expect(latestRun(make({ runs: undefined } as never))).toBeNull();
    const one = make({}, [run('a', 'done', '2026-11-20T10:00:00Z')]);
    expect(latestRun(one)?.id).toBe('a');
    expect(liveRun(one)).toBeNull();
    const many = make({}, [
      run('c', 'running', '2026-11-23T10:00:00Z'),
      run('a', 'queued', '2026-11-20T10:00:00Z'),
      run('b', 'failed', '2026-11-25T10:00:00Z'),
    ]);
    expect(latestRun(many)?.id).toBe('b');
    expect(liveRun(many)?.id).toBe('c');
  });
});

describe('reopenPlacement', () => {
  it('summary: a build Run needs_you, selected and latest', () => {
    expect(reopenPlacement(make(), 2)).toBe('summary');
  });

  it('summary: a failed initiative with a failed latest Run', () => {
    const d = make({ status: 'failed', reason: '' }, [
      run('run-b', 'failed', '2026-11-22T10:00:00Z'),
    ]);
    expect(reopenPlacement(d, 2)).toBe('summary');
  });

  it('null: spec selected, not the latest Run, no run_id, interactive', () => {
    expect(reopenPlacement(make(), 1)).toBeNull();
    const old = make({}, [
      run('run-b', 'needs_you', '2026-11-22T10:00:00Z'),
      run('run-x', 'done', '2026-11-23T10:00:00Z'),
    ]);
    expect(reopenPlacement(old, 2)).toBeNull();
    const none = make({
      workflows: [workflow('spec', 1), workflow('build', 2, { type: 'auto', run_id: null })],
    } as never);
    expect(reopenPlacement(none, 2)).toBeNull();
    const interactive = make({
      workflows: [workflow('spec', 1), workflow('build', 2, { run_id: 'run-b' })],
    } as never);
    expect(reopenPlacement(interactive, 2)).toBeNull();
  });

  it('null for running, done and cancelled', () => {
    for (const status of ['running', 'done', 'cancelled']) {
      expect(reopenPlacement(make({ status } as never), 2)).toBeNull();
    }
  });

  it('banner: a blocked advance, with either selection', () => {
    const d = make({ reason: 'preflight: harness: not ready' }, [
      run('run-s', 'done', '2026-11-20T10:00:00Z'),
    ]);
    expect(reopenPlacement(d, 1)).toBe('banner');
    expect(reopenPlacement(d, 2)).toBe('banner');
  });
});

describe('spec steps', () => {
  it('specWorkflow is the first interactive workflow with a conversation step', () => {
    expect(specWorkflow(make())?.workflow).toBe('spec');
    const auto = step('gate', { kind: 'automatic' } as Partial<Step>);
    const d = make({
      workflows: [workflow('x', 1, { steps: [auto] }), workflow('spec', 2, { steps: [step('a')] })],
    } as never);
    expect(specWorkflow(d)?.workflow).toBe('spec');
    expect(specWorkflow(make({ workflows: [] } as never))).toBeNull();
  });

  it('labels: number or position.index, agent when set, automatic steps skipped', () => {
    const d = make({
      workflows: [
        workflow('spec', 1, {
          steps: [
            step('intake', { number: '1.1', agent: 'intake-router' }),
            step('gate', { kind: 'automatic' } as Partial<Step>),
            step('ux', { number: '', agent: null }),
          ],
        }),
      ],
    } as never);
    expect(reopenSteps(d)).toEqual([
      { id: 'intake', label: '1.1 intake · intake-router' },
      { id: 'ux', label: '1.3 ux' },
    ]);
    expect(reopenSteps(make({ workflows: [] } as never))).toEqual([]);
  });
});

describe('reason, question, run, mechanism, labels', () => {
  it('reopenReason', () => {
    const d = make();
    expect(reopenReason(d, 'build', 'run-b')).toBe(
      'build stopped: verify failed: make test exited 2',
    );
    expect(reopenReason(make({ reason: '' }), 'build', RUN_B)).toBe(
      'build stopped: Run 0193…bb02 failed',
    );
    expect(reopenReason(d, 'advance', null)).toBe(
      'advance blocked: verify failed: make test exited 2',
    );
  });

  it('reopenQuestion', () => {
    expect(reopenQuestion('build')).toBe('Which spec step does this build stop come from?');
    expect(reopenQuestion('advance')).toBe('Which spec step does this stop come from?');
  });

  it('reopenRunId', () => {
    const d = make({}, [run('live', 'running', '2026-11-22T10:00:00Z')]);
    expect(reopenRunId(d, 'build', 'run-b')).toBe('run-b');
    expect(reopenRunId(d, 'advance', 'run-b')).toBe('live');
    expect(reopenRunId(make({}, []), 'advance', null)).toBeNull();
    expect(reopenRunId(make({}, []), 'build', null)).toBeNull();
  });

  it('reopenMechanism', () => {
    const d = make({ round: 2 } as never);
    expect(reopenMechanism(d, RUN_B, null)).toBe(
      'Run 0193…bb02 is cancelled and keeps its page. The step you choose reopens as round 3 with this stop as its first turn, on spec/familio-dessin-v2, created from main if it was deleted after the merge. Then the gate, the merge and the build run again.',
    );
    expect(reopenMechanism(d, null, 'tech')).toBe(
      'tech reopens as round 3 with this stop as its first turn, on spec/familio-dessin-v2, created from main if it was deleted after the merge. Then the gate, the merge and the build run again.',
    );
  });

  it('labels and constants', () => {
    expect(reopenLabel(null)).toBe('Reopen step');
    expect(reopenLabel('tech')).toBe('Reopen tech');
    expect(REOPEN_HEAD).toBe('REOPEN A SPEC STEP');
    expect(KEEP_LABEL).toBe('Keep the build stopped');
  });

  it('freshBranchLine', () => {
    const at = (branch: string) =>
      step('tech', { reopened_after: { workflow: 'build', branch } } as unknown as Partial<Step>);
    expect(freshBranchLine(at('created'), 'x')).toBe('on a fresh spec/x from main');
    expect(freshBranchLine(at('attached'), 'x')).toBeNull();
    expect(freshBranchLine(step('tech', { reopened_after: null } as never), 'x')).toBeNull();
    expect(freshBranchLine(step('tech'), 'x')).toBeNull();
  });
});
