/**
 * Fixtures for the guardrail strip split (epic 2 story 3): graphs that carry `run_order`,
 * owned by the suite — no shipped template is read here (hard rule 6).
 */
import type { components } from '../../src/api/schema';
import { group, node, step } from './run-graph';

type RunGraphOut = components['schemas']['RunGraphOut'];
type RunNodeOut = components['schemas']['RunNodeOut'];
type RunOrderFrameOut = components['schemas']['RunOrderFrameOut'];
type StepRowOut = components['schemas']['StepRowOut'];

const DONE = { status: 'done', token: 'DON' } as const;
const QUEUED = { status: 'queued', token: 'QUE' } as const;

const STORY = 'epics[0].stories[0]';

function agent(id: string, label: string, overrides: Partial<RunNodeOut> = {}): RunNodeOut {
  return node(id, { kind: 'agent', gate: 'liveness', agent: true, label, ...overrides });
}

function rows(
  list: [string, 'BEFORE' | 'AGENT' | 'AFTER', string, number][],
): RunOrderFrameOut['rows'] {
  return list.map(([path, phase, label, seq]) => ({
    path,
    phase,
    label,
    seq,
    kind: phase === 'AGENT' ? 'agent' : 'shell',
    token: 'QUE',
  }));
}

/** `sync (BEFORE), build (AGENT), verify, commit, push (AFTER)` on one story of one epic. */
export function storyOrderGraph(): RunGraphOut {
  const members = ['sync', 'build', 'verify', 'commit', 'push'].map((s) => `${STORY}.${s}`);
  const nodes: RunNodeOut[] = [
    node('root', { kind: 'initiative', label: 'initiative', status: 'running', token: 'RUN' }),
    node(`${STORY}.sync`, { label: 'epic 1 · story 1 · sync', seq: 1, ...DONE }),
    agent(`${STORY}.build`, 'epic 1 · story 1 · build', {
      seq: 2,
      attempt_n: 2,
      ...DONE,
    }),
    node(`${STORY}.verify`, { label: 'epic 1 · story 1 · verify', seq: 3, ...DONE }),
    node(`${STORY}.commit`, { label: 'epic 1 · story 1 · commit', seq: 4, ...DONE }),
    node(`${STORY}.push`, { label: 'epic 1 · story 1 · push', seq: 5, attempt_n: 3, ...QUEUED }),
  ];
  const groups = [group('epics[0]', members), group(STORY, members)];
  return {
    nodes,
    edges: [],
    groups,
    run_order: [
      {
        frame: STORY,
        rows: rows([
          [`${STORY}.sync`, 'BEFORE', 'sync', 1],
          [`${STORY}.build`, 'AGENT', 'build', 2],
          [`${STORY}.verify`, 'AFTER', 'verify', 3],
          [`${STORY}.commit`, 'AFTER', 'commit', 4],
          [`${STORY}.push`, 'AFTER', 'push', 5],
        ]),
      },
    ],
  };
}

/** An epic with six own rows around one story holding an agent. */
export function epicOrderGraph(): RunGraphOut {
  const own = ['branch', 'setup', 'baseline', 'commit-e2e', 'e2e', 'push'].map(
    (s) => `epics[0].${s}`,
  );
  const nodes: RunNodeOut[] = [
    node('root', { kind: 'initiative', label: 'initiative', status: 'running', token: 'RUN' }),
    ...own
      .slice(0, 3)
      .map((id, i) => node(id, { label: `epic 1 · ${id.split('.')[1]}`, seq: i + 1, ...DONE })),
    agent(`${STORY}.build`, 'epic 1 · story 1 · build', { seq: 4, ...DONE }),
    ...own
      .slice(3)
      .map((id, i) => node(id, { label: `epic 1 · ${id.split('.')[1]}`, seq: i + 5, ...QUEUED })),
  ];
  return {
    nodes,
    edges: [],
    groups: [group('epics[0]', [...own, `${STORY}.build`]), group(STORY, [`${STORY}.build`])],
    run_order: [
      {
        frame: 'epics[0]',
        rows: rows([
          ['epics[0].branch', 'BEFORE', 'branch', 1],
          ['epics[0].setup', 'BEFORE', 'setup', 2],
          ['epics[0].baseline', 'BEFORE', 'baseline', 3],
          ['epics[0].commit-e2e', 'AFTER', 'commit-e2e', 5],
          ['epics[0].e2e', 'AFTER', 'e2e', 6],
          ['epics[0].push', 'AFTER', 'push', 7],
        ]),
      },
      { frame: STORY, rows: rows([[`${STORY}.build`, 'AGENT', 'build', 4]]) },
    ],
  };
}

/** Eight-row epic: `n` BEFORE rows then one AFTER row; the row at `blockedAt` is blocked. */
export function wideEpicGraph(before: number, blockedAt: number): RunGraphOut {
  const ids = Array.from({ length: before }, (_, i) => `epics[0].b${i}`);
  const after = 'epics[0].fin';
  const nodes: RunNodeOut[] = [
    node('root', { kind: 'initiative', label: 'initiative', status: 'running', token: 'RUN' }),
    ...ids.map((id, i) =>
      node(id, {
        label: `epic 1 · b${i}`,
        seq: i + 1,
        ...(i === blockedAt ? { status: 'blocked', token: 'BLK' } : DONE),
      }),
    ),
    node(after, { label: 'epic 1 · fin', seq: before + 1, ...QUEUED }),
  ];
  return {
    nodes,
    edges: [],
    groups: [group('epics[0]', [...ids, after])],
    run_order: [
      {
        frame: 'epics[0]',
        rows: [
          ...rows(ids.map((id, i) => [id, 'BEFORE', `b${i}`, i + 1])),
          ...rows([[after, 'AFTER', 'fin', before + 1]]),
        ],
      },
    ],
  };
}

export function orderSteps(graph: RunGraphOut): StepRowOut[] {
  return graph.nodes.map((n, i) => step(n.id, { seq: n.seq ?? i + 1, label: n.label }));
}
