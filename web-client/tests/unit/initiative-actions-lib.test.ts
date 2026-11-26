/** Story 11.4: the pure helpers of lib/initiative/actions.ts. */
import { describe, expect, it } from 'vitest';

import {
  cancelLines,
  cancelledStateLine,
  forceHead,
  forceMechanism,
  forceParkSeq,
  forceQuestion,
  forceTarget,
  forcedLine,
  keepLabel,
  showsCancel,
  startLabel,
} from '../../src/lib/initiative/actions';
import { detail, step, workflow, type Detail, type Step } from './initiative-fixtures';

const parked = (over: Partial<Step> = {}): Partial<Step> => ({
  kind: 'conversation',
  park_kind: 'conversation',
  park_seq: 7,
  run_id: 'run-s',
  ...over,
});

function build(
  steps: Step[],
  current = 'ux',
  over: Partial<Detail> = {},
  wf: Record<string, unknown> = {},
): Detail {
  return detail({
    current_step: current,
    workflows: [
      workflow('spec', 1, { steps, run_id: '0193e5f6-0000-7000-8000-000000008c02', ...wf }),
      workflow('build', 2, { type: 'auto' }),
    ],
    ...over,
  });
}

const base = (): Step[] => [
  step('product'),
  step('arch'),
  step('ux', parked()),
  step('tech'),
  step('gate', { kind: 'automatic' }),
  step('merge', { kind: 'automatic' }),
];
const spec = (d: Detail) => d.workflows[0];

describe('forceTarget', () => {
  it('names the next conversation step when the current one is parked', () => {
    const d = build(base());
    expect(forceTarget(d, spec(d))).toBe('tech');
    expect(forceParkSeq(d, spec(d))).toBe(7);
  });

  it('is null for a workflow that is not current', () => {
    const d = build(base(), 'ux', { current_position: 2 });
    expect(forceTarget(d, spec(d))).toBeNull();
  });

  it('is null for an auto workflow', () => {
    const d = build(base(), 'ux', {}, { type: 'auto' });
    expect(forceTarget(d, spec(d))).toBeNull();
  });

  it('is null when the current step is not found', () => {
    const d = build(base(), 'nope');
    expect(forceTarget(d, spec(d))).toBeNull();
    expect(forceParkSeq(d, spec(d))).toBeNull();
  });

  it('is null when the current step is automatic', () => {
    const steps = base();
    steps[2] = step('ux', parked({ kind: 'automatic' }));
    const d = build(steps);
    expect(forceTarget(d, spec(d))).toBeNull();
  });

  it.each([null, 'merge_conflict'] as const)('is null when parked on %s', (k) => {
    const steps = base();
    steps[2] = step('ux', parked({ park_kind: k }));
    const d = build(steps);
    expect(forceTarget(d, spec(d))).toBeNull();
  });

  it('is null without a park_seq', () => {
    const steps = base();
    steps[2] = step('ux', parked({ park_seq: null }));
    const d = build(steps);
    expect(forceTarget(d, spec(d))).toBeNull();
  });

  it('is null on the last step and when the next is automatic', () => {
    const last = build(base(), 'merge');
    expect(forceTarget(last, spec(last))).toBeNull();
    const steps = base();
    steps[3] = step('tech', parked());
    const d = build(steps, 'tech');
    expect(forceTarget(d, spec(d))).toBeNull();
  });

  it('is null when a named round leaves the next step out, and shown when it names it', () => {
    const out = build(base(), 'ux', { owners: ['ux'] });
    expect(forceTarget(out, spec(out))).toBeNull();
    const named = build(base(), 'ux', { owners: ['ux', 'tech'] });
    expect(forceTarget(named, spec(named))).toBe('tech');
  });

  it('is null on a cancelled initiative', () => {
    const d = build(base(), 'ux', { status: 'cancelled' });
    expect(forceTarget(d, spec(d))).toBeNull();
  });
});

describe('force modal lines', () => {
  it('gives the head, question and labels', () => {
    expect(forceHead('tech')).toBe('START TECH NOW');
    expect(forceQuestion('ux')).toBe(
      'Are you sure? If step «UX» is not done this workflow might fail.',
    );
    expect(keepLabel('ux')).toBe('Keep ux open');
    expect(startLabel('tech')).toBe('Start tech');
  });

  it('names the following workflow only when there is one', () => {
    const head =
      'The UX step closes as skipped, forced; its conversation and its draft files are kept. Tech starts with what is on spec/familio-dessin-v2 now.';
    expect(forceMechanism('ux', 'tech', 'familio-dessin-v2', 'spec', 'build')).toBe(
      `${head} The gate is never forced, so build cannot start before spec passes it.`,
    );
    expect(forceMechanism('ux', 'tech', 'familio-dessin-v2', 'spec', null)).toBe(head);
  });
});

describe('cancel', () => {
  it('shows the control unless done or cancelled', () => {
    expect(showsCancel('running')).toBe(true);
    expect(showsCancel('waiting for her')).toBe(true);
    expect(showsCancel('done')).toBe(false);
    expect(showsCancel('cancelled')).toBe(false);
  });

  const sess = (over: Record<string, unknown> = {}) => ({
    workflow: 'spec',
    step: 'ux',
    kind: 'session',
    state: 'open',
    id: 's1',
    ...over,
  });
  const other = [
    'spec/familio-dessin-v2 is deleted',
    'Files already merged into main stay; nothing is removed from main',
    'The slug familio-dessin-v2 is free again',
  ];

  it('lists the open session', () => {
    const d = build(base(), 'ux', { sessions: [sess()] } as Partial<Detail>);
    expect(cancelLines(d)).toEqual([
      other[0],
      'The open ux session is cancelled',
      other[1],
      other[2],
    ]);
  });

  it.each([{ state: 'closed' }, { step: 'arch' }, { kind: 'run' }])(
    'falls back to the Run when the session is %o',
    (over) => {
      const d = build(base(), 'ux', { sessions: [sess(over)] } as Partial<Detail>);
      expect(cancelLines(d)[1]).toBe('Run 0193…8c02 is cancelled');
    },
  );

  it('lists three lines when there is neither', () => {
    const d = build(base(), 'ux', {}, { run_id: null });
    expect(cancelLines(d)).toEqual(other);
  });

  it('ignores a session on an auto current workflow', () => {
    const d = build(base(), 'ux', { sessions: [sess()] } as Partial<Detail>, { type: 'auto' });
    expect(cancelLines(d)[1]).toBe('Run 0193…8c02 is cancelled');
  });

  it('reads the cancelled state line with and without a time', () => {
    const d = build(base(), 'ux', { step: 'ux', cancelled_at: '2026-11-22T21:50:00Z' });
    expect(cancelledStateLine(d)).toBe('cancelled at ux · 21:50');
    expect(cancelledStateLine({ ...d, cancelled_at: null })).toBe('cancelled at ux');
  });
});

describe('forcedLine', () => {
  const tech = step('tech');
  const prev = (over: Partial<Step>) => step('ux', { token: 'SKP', ...over });

  it('reads the time the API wrote', () => {
    expect(forcedLine(prev({ line: 'skipped, forced · 21:44' }), tech, 'familio-dessin-v2')).toBe(
      'ux skipped, forced at 21:44 · its files on spec/familio-dessin-v2 are what tech reads',
    );
  });

  it('drops the time when the line has none', () => {
    expect(forcedLine(prev({ line: 'skipped, forced' }), tech, 'familio-dessin-v2')).toBe(
      'ux skipped, forced · its files on spec/familio-dessin-v2 are what tech reads',
    );
  });

  it('is null for a null or non-SKP previous step', () => {
    expect(forcedLine(null, tech, 's')).toBeNull();
    expect(forcedLine(prev({ token: 'DON' }), tech, 's')).toBeNull();
  });
});
