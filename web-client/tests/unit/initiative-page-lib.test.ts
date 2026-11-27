/** Story 11.1: the pure helpers of `lib/initiative/page.ts`. */
import { describe, expect, it } from 'vitest';

import type { components } from '../../src/api/schema';
import {
  defaultSelection,
  headerMetaLine,
  headerPositionLine,
  headerStateLine,
  isInteractive,
  notStartedLines,
  parseWorkflowParam,
  pollFast,
  previousWorkflowName,
  showNow,
  statusTokenWord,
  stepAnnounce,
  stepEyebrow,
  stepStatusWord,
  workflowEyebrow,
  workflowMicro,
} from '../../src/lib/initiative/page';

type Detail = components['schemas']['InitiativeDetailOut'];
type Workflow = components['schemas']['DetailWorkflowOut'];
type Step = components['schemas']['DetailStepOut'];

const step = (id: string, over: Partial<Step> = {}): Step =>
  ({
    id,
    kind: 'conversation',
    status: 'planned',
    token: 'QUE',
    line: '',
    agent: null,
    turns: [],
    ...over,
  }) as unknown as Step;

const wf = (workflow: string, position: number, over: Partial<Workflow> = {}): Workflow =>
  ({
    workflow,
    position,
    type: 'interactive',
    template: 'spec-flow',
    version: 3,
    run_id: null,
    token: null,
    line: '',
    steps: [],
    files: [],
    status: null,
    ...over,
  }) as unknown as Workflow;

const detail = (over: Partial<Detail> = {}): Detail =>
  ({
    status: 'running',
    workflow: 'spec',
    step: 'ux',
    current_step: 'ux',
    current_position: 1,
    workflow_count: 2,
    attention: 'your_turn',
    reason: '',
    hub: { id: 'h', slug: 'hub-repo' },
    folder: 'initiatives/x',
    package: 'pkg',
    sequence_fixed_at: '2026-11-20T10:00:00Z',
    created_at: '2026-11-19T09:00:00Z',
    runs: [],
    workflows: [
      wf('spec', 1, {
        steps: ['product', 'arch', 'ux', 'a', 'b', 'c'].map((id) => step(id)),
      }),
      wf('build', 2, { type: 'auto' }),
    ],
    ...over,
  }) as unknown as Detail;

describe('headerStateLine', () => {
  it('ends in your turn for attention your_turn', () => {
    expect(headerStateLine(detail())).toBe('running · spec · ux · your turn');
  });
  it('prefers the reason', () => {
    expect(headerStateLine(detail({ reason: 'budget reached' }))).toBe(
      'running · spec · ux · budget reached',
    );
  });
  it('says agent answering for answering and queued', () => {
    expect(headerStateLine(detail({ attention: 'answering' }))).toMatch(/ · agent answering$/);
    expect(headerStateLine(detail({ attention: 'queued' }))).toMatch(/ · agent answering$/);
  });
  it('has no suffix otherwise', () => {
    expect(headerStateLine(detail({ attention: null }))).toBe('running · spec · ux');
    expect(headerStateLine(detail({ attention: 'blocked' }))).toBe('running · spec · ux');
  });
  it('maps waiting for her to needs you', () => {
    expect(headerStateLine(detail({ status: 'waiting for her', attention: null }))).toBe(
      'needs you · spec · ux',
    );
  });
});

describe('headerPositionLine', () => {
  it('names the step position of an interactive current workflow', () => {
    expect(headerPositionLine(detail())).toBe('workflow 1 of 2 · spec · step 3 of 6');
  });
  it('drops the step part for an auto workflow', () => {
    const d = detail({ current_position: 2, workflow: 'build', current_step: null });
    expect(headerPositionLine(d)).toBe('workflow 2 of 2 · build');
  });
  it('drops the step part when the step is unknown', () => {
    expect(headerPositionLine(detail({ current_step: 'zzz' }))).toBe('workflow 1 of 2 · spec');
    expect(headerPositionLine(detail({ current_step: null }))).toBe('workflow 1 of 2 · spec');
  });
  it('drops the step part when no workflow holds the current position', () => {
    expect(headerPositionLine(detail({ current_position: 9 }))).toBe('workflow 9 of 2 · spec');
  });
});

describe('headerMetaLine', () => {
  it('reads hub, folder, package, count, fixed date, created', () => {
    expect(headerMetaLine(detail())).toBe(
      'hub hub-repo · folder initiatives/x · package pkg (2 workflows, fixed 2026-11-20) · created 2026-11-19T09:00:00Z',
    );
  });
  it('omits fixed and hub when null', () => {
    expect(headerMetaLine(detail({ sequence_fixed_at: null, hub: null }))).toBe(
      'folder initiatives/x · package pkg (2 workflows) · created 2026-11-19T09:00:00Z',
    );
  });
});

describe('workflow and step copy', () => {
  it('eyebrows', () => {
    expect(workflowEyebrow(wf('spec', 1))).toBe('WORKFLOW 1 · INTERACTIVE');
    expect(workflowEyebrow(wf('build', 2, { type: 'auto' }))).toBe('WORKFLOW 2 · AUTO');
    expect(stepEyebrow(1, 3, 'conversation')).toBe('1.3 · CONVERSATION');
    expect(stepEyebrow(1, 4, 'automatic')).toBe('1.4 · AUTOMATIC');
  });
  it('micro text', () => {
    const w = wf('spec', 1, { steps: [step('a'), step('b')] });
    expect(workflowMicro(w)).toBe('spec-flow@3 · 2 steps');
    expect(workflowMicro(wf('build', 2, { type: 'auto' }))).toBe('spec-flow@3');
  });
  it('isInteractive', () => {
    expect(isInteractive(wf('a', 1))).toBe(true);
    expect(isInteractive(wf('a', 1, { type: 'auto' }))).toBe(false);
  });
  it('stepStatusWord and stepAnnounce', () => {
    expect(stepStatusWord('waiting for her')).toBe('needs you');
    expect(stepStatusWord('running')).toBe('running');
    expect(stepAnnounce(3, step('ux', { status: 'running', line: 'your turn · 14 turns' }))).toBe(
      '3 ux, running, your turn · 14 turns',
    );
  });
});

describe('status and polling', () => {
  it('statusTokenWord is the EXPERIENCE § 3 table', () => {
    expect(statusTokenWord('running')).toEqual({ token: 'RUN', word: 'running' });
    expect(statusTokenWord('waiting for her')).toEqual({ token: 'BLK', word: 'needs you' });
    expect(statusTokenWord('done')).toEqual({ token: 'DON', word: 'done' });
    expect(statusTokenWord('failed')).toEqual({ token: 'ERR', word: 'failed' });
    expect(statusTokenWord('cancelled')).toEqual({ token: 'CAN', word: 'cancelled' });
  });
  it('showNow is false on done and cancelled', () => {
    expect(showNow('running')).toBe(true);
    expect(showNow('waiting for her')).toBe(true);
    expect(showNow('done')).toBe(false);
    expect(showNow('cancelled')).toBe(false);
  });
  it('pollFast on answering, queued, or an active run', () => {
    expect(pollFast(detail({ attention: null }))).toBe(false);
    expect(pollFast(detail({ attention: 'answering' }))).toBe(true);
    expect(pollFast(detail({ attention: 'queued' }))).toBe(true);
    const run = (status: string) => ({ status }) as unknown as Detail['runs'][number];
    expect(pollFast(detail({ attention: null, runs: [run('running')] }))).toBe(true);
    expect(pollFast(detail({ attention: null, runs: [run('queued')] }))).toBe(true);
    expect(pollFast(detail({ attention: null, runs: [run('done')] }))).toBe(false);
  });
});

describe('parseWorkflowParam', () => {
  it('parses a positive integer', () => {
    expect(parseWorkflowParam('2')).toBe(2);
  });
  it.each([null, '', '0', '-1', '1.5', 'x'])('gives null for %j', (raw) => {
    expect(parseWorkflowParam(raw)).toBeNull();
  });
});

describe('defaultSelection', () => {
  it('uses the current workflow and its current step', () => {
    expect(defaultSelection(detail(), null)).toEqual({ position: 1, stepId: 'ux' });
  });
  it('uses the named workflow, with no step for an auto one', () => {
    expect(defaultSelection(detail(), 2)).toEqual({ position: 2, stepId: null });
  });
  it('falls back to current_position when the name matches no workflow', () => {
    expect(defaultSelection(detail(), 7)).toEqual({ position: 1, stepId: 'ux' });
  });
  it('gives no step in a named workflow that is not current, even on a shared step id', () => {
    const d = detail();
    const other = { ...d.workflows[0], workflow: 'spec-b', position: 3 };
    expect(defaultSelection({ ...d, workflows: [...d.workflows, other] }, 3)).toEqual({
      position: 3,
      stepId: null,
    });
  });
  it('gives no step when current_step is not in the selected workflow', () => {
    expect(defaultSelection(detail({ current_step: 'zzz' }), null)).toEqual({
      position: 1,
      stepId: null,
    });
    expect(defaultSelection(detail({ current_step: null }), null)).toEqual({
      position: 1,
      stepId: null,
    });
  });
});

describe('previousWorkflowName and notStartedLines', () => {
  const d = detail();
  it('names the workflow before a position', () => {
    expect(previousWorkflowName(d.workflows, 2)).toBe('spec');
    expect(previousWorkflowName(d.workflows, 1)).toBeNull();
  });
  const project = (budget: string | null) =>
    ({
      default_autonomy: 'auto',
      default_model: 'claude-opus-5-5',
      default_budget_usd: budget,
    }) as unknown as components['schemas']['ProjectRead'];
  it('states when it starts and the project defaults', () => {
    expect(notStartedLines(d.workflows[1], 'spec', project('60.00'))).toEqual([
      'not started',
      'starts by itself when spec is done',
      'template spec-flow@3 · auto',
      'project defaults: autonomy auto · claude-opus-5-5 · budget $60.00',
    ]);
  });
  it('states a missing budget', () => {
    expect(notStartedLines(d.workflows[1], 'spec', project(null))[3]).toBe(
      'project defaults: autonomy auto · claude-opus-5-5 · no default budget — the build will stop and ask',
    );
  });
  it('omits the defaults line without a project', () => {
    expect(notStartedLines(d.workflows[1], null, null)).toEqual([
      'not started',
      'template spec-flow@3 · auto',
    ]);
  });
});
