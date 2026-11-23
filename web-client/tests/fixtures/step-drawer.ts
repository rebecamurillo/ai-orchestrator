/** Typed `StepDrawerOut` builders for the step-drawer suites (epic 2 story 2). */
import type { components } from '../../src/api/schema';

export type StepDrawerOut = components['schemas']['StepDrawerOut'];

interface Overrides {
  header?: Partial<StepDrawerOut['header']>;
  files_read?: StepDrawerOut['files_read'];
  files_written?: StepDrawerOut['files_written'];
  run_order?: StepDrawerOut['run_order'];
  log?: StepDrawerOut['log'];
  attempts?: StepDrawerOut['attempts'];
}

const ORDER: NonNullable<StepDrawerOut['run_order']> = {
  frame: 'epics[0].stories[0]',
  rows: [12, 13, 14].map((seq, i) => ({
    kind: ['shell', 'agent', 'shell'][i]!,
    label: ['sync', 'build', 'verify'][i]!,
    path: `epics[0].stories[0].${['sync', 'build', 'verify'][i]}`,
    phase: (['BEFORE', 'AGENT', 'AFTER'] as const)[i]!,
    seq,
    token: ['DON', 'RUN', 'QUE'][i]!,
    with_resolved: {},
  })),
};

export function agentDrawer(overrides: Overrides = {}): StepDrawerOut {
  return {
    attempts: overrides.attempts ?? [
      { n: 1, status: 'error' },
      { n: 2, status: 'running' },
    ],
    files_read: overrides.files_read ?? { state: 'listed', paths: ['src/a.ts', 'src/b.ts'] },
    files_written: overrides.files_written ?? {
      state: 'files',
      commit: null,
      refs: [],
      files: [{ path: 'src/a.ts', added: 3, removed: 1 }],
    },
    header: {
      cost_usd: '1.25',
      ended_at: null,
      exit_code: null,
      gate: 'liveness',
      kind: 'agent',
      label: 'build',
      n: 2,
      path: 'epics[0].stories[0].build',
      seq: 13,
      started_at: null,
      status: 'running',
      token: 'RUN',
      ...overrides.header,
    },
    log: overrides.log ?? {
      attempt_id: 'att-2',
      reason: null,
      removed_at: null,
      state: 'text',
    },
    run_order: overrides.run_order === undefined ? ORDER : overrides.run_order,
  };
}

export function shellDrawer(overrides: Overrides = {}): StepDrawerOut {
  return agentDrawer({
    attempts: [{ n: 1, status: 'done' }],
    files_read: { state: 'not_recorded', paths: [] },
    files_written: { state: 'none', commit: null, refs: [], files: [] },
    ...overrides,
    header: {
      kind: 'shell',
      gate: 'deterministic',
      label: 'verify',
      path: 'epics[0].stories[0].verify',
      seq: 14,
      n: 1,
      cost_usd: null,
      started_at: '2026-11-23T10:00:00Z',
      ended_at: '2026-11-23T10:02:05Z',
      exit_code: 0,
      status: 'done',
      token: 'DON',
      ...overrides.header,
    },
  });
}
