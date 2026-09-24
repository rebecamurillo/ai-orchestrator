/**
 * Fixtures for the v3 run diagram, with the **real** id shape the backend emits — the one
 * source for both suites.
 *
 * `application/graph.py::_group_prefixes` writes bracket-index frames — `epics[0]`,
 * `epics[0].stories[1]` — and every row's id is its `step_run.path` verbatim. The previous
 * build's fixtures used a slugged `epic-1/story-4-1` shape that no backend ever produced,
 * which is exactly why its regex-based tree matched nothing in production and everything in
 * its own tests. These fixtures are owned by the suite (no shipped template is read here,
 * hard rule 6) and they are the shape the wire actually carries.
 *
 * It lives outside `tests/unit/` because `tests/e2e/run-diagram.spec.ts` reads it too: the
 * two suites each had their own `twoEpicGraph` for one iteration and they had already
 * drifted, which is how a unit suite goes green over a graph the browser never sees.
 *
 * Two shapes:
 * - `twoEpicGraph()` — the artboard's run: two epics of two stories, a third collapsed epic,
 *   epic-level agents (`spec-gate`, `gen-e2e`, `retro`) interleaved with the stories in plan
 *   order, deterministic rows around them, `epics[1].stories[0].build` current.
 * - `frameLessGraph()` — a `story@1`-shaped plan: bare `sync`, `build`, `verify`,
 *   `commit-guard` rows and **no groups at all**, which is what `story@1`, `task@1` and
 *   `repo-init@1` really send and what the four-rank model got wrong.
 */
import type { components } from '../../src/api/schema';

type RunGraphOut = components['schemas']['RunGraphOut'];
type RunNodeOut = components['schemas']['RunNodeOut'];
type RunGroupOut = components['schemas']['RunGroupOut'];
type StepRowOut = components['schemas']['StepRowOut'];

export function node(id: string, overrides: Partial<RunNodeOut> = {}): RunNodeOut {
  return {
    id,
    kind: 'shell',
    label: id,
    gate: 'deterministic',
    agent: false,
    human: false,
    call: null,
    status: 'queued',
    token: 'QUE',
    current: false,
    ...overrides,
  };
}

export function group(
  id: string,
  members: string[],
  overrides: Partial<RunGroupOut> = {},
): RunGroupOut {
  return {
    id,
    kind: 'for_each',
    label: id,
    members,
    status: 'queued',
    k: 0,
    n: members.length,
    ...overrides,
  };
}

export function step(path: string, overrides: Partial<StepRowOut> = {}): StepRowOut {
  return {
    seq: 1,
    path,
    label: path,
    kind: 'shell',
    gate: 'deterministic',
    status: 'queued',
    token: 'QUE',
    reason: null,
    attempts: 0,
    latest: null,
    ...overrides,
  };
}

const DONE = { status: 'done', token: 'DON' } as const;
const QUEUED = { status: 'queued', token: 'QUE' } as const;

/** One story frame: three guardrail rows around one agent row. */
function storyNodes(frame: string, label: string, state: Partial<RunNodeOut>): RunNodeOut[] {
  return [
    node(`${frame}.sync`, { label: `${label} · sync`, ...state }),
    node(`${frame}.build`, {
      kind: 'agent',
      gate: 'liveness',
      agent: true,
      label: `${label} · build`,
      ...state,
    }),
    node(`${frame}.verify`, { label: `${label} · verify`, ...state }),
    node(`${frame}.commit-guard`, { label: `${label} · commit-guard`, ...state }),
  ];
}

function storyMembers(frame: string): string[] {
  return [`${frame}.sync`, `${frame}.build`, `${frame}.verify`, `${frame}.commit-guard`];
}

/** Two epics of two stories, plus a queued third epic; `epics[1].stories[0].build` is current. */
export function twoEpicGraph(currentBuild: Partial<RunNodeOut> = {}): RunGraphOut {
  const nodes: RunNodeOut[] = [
    node('root', { kind: 'initiative', label: 'initiative', status: 'running', token: 'RUN' }),
    node('plan', { kind: 'plan.check', label: 'plan', ...DONE }),

    node('epics[0].branch', { label: 'epic 1 · branch', ...DONE }),
    node('epics[0].setup', { label: 'epic 1 · setup', ...DONE }),
    node('epics[0].baseline', { label: 'epic 1 · baseline', ...DONE }),
    node('epics[0].spec-gate', {
      kind: 'agent',
      agent: true,
      label: 'epic 1 · spec-gate',
      ...DONE,
    }),
    ...storyNodes('epics[0].stories[0]', 'epic 1 · story 1-1', DONE),
    ...storyNodes('epics[0].stories[1]', 'epic 1 · story 1-2', DONE),
    node('epics[0].gen-e2e', { kind: 'agent', agent: true, label: 'epic 1 · gen-e2e', ...DONE }),
    node('epics[0].retro', { kind: 'agent', agent: true, label: 'epic 1 · retro', ...DONE }),

    node('epics[1].branch', { label: 'epic 2 · branch', ...DONE }),
    node('epics[1].setup', { label: 'epic 2 · setup', ...DONE }),
    node('epics[1].baseline', { label: 'epic 2 · baseline', ...DONE }),
    node('epics[1].spec-gate', {
      kind: 'agent',
      agent: true,
      label: 'epic 2 · spec-gate',
      ...DONE,
    }),
    node('epics[1].stories[0].sync', { label: 'epic 2 · story 2-1 · sync', ...DONE }),
    node('epics[1].stories[0].build', {
      kind: 'agent',
      gate: 'liveness',
      agent: true,
      label: 'epic 2 · story 2-1 · build',
      status: 'running',
      token: 'RUN',
      current: true,
      ...currentBuild,
    }),
    node('epics[1].stories[0].verify', { label: 'epic 2 · story 2-1 · verify', ...QUEUED }),
    node('epics[1].stories[0].commit-guard', {
      label: 'epic 2 · story 2-1 · commit-guard',
      ...QUEUED,
    }),
    ...storyNodes('epics[1].stories[1]', 'epic 2 · story 2-2', QUEUED),
    node('epics[1].gen-e2e', { kind: 'agent', agent: true, label: 'epic 2 · gen-e2e', ...QUEUED }),
    node('epics[1].retro', { kind: 'agent', agent: true, label: 'epic 2 · retro', ...QUEUED }),

    node('epics[2].branch', { label: 'epic 3 · branch', ...QUEUED }),
    ...storyNodes('epics[2].stories[0]', 'epic 3 · story 3-1', QUEUED),
  ];

  const groups: RunGroupOut[] = [
    group(
      'epics[0]',
      [
        'epics[0].branch',
        'epics[0].setup',
        'epics[0].baseline',
        'epics[0].spec-gate',
        ...storyMembers('epics[0].stories[0]'),
        ...storyMembers('epics[0].stories[1]'),
        'epics[0].gen-e2e',
        'epics[0].retro',
      ],
      { status: 'done', k: 14, n: 14 },
    ),
    group('epics[0].stories[0]', storyMembers('epics[0].stories[0]'), {
      status: 'done',
      k: 4,
      n: 4,
    }),
    group('epics[0].stories[1]', storyMembers('epics[0].stories[1]'), {
      status: 'done',
      k: 4,
      n: 4,
    }),
    group(
      'epics[1]',
      [
        'epics[1].branch',
        'epics[1].setup',
        'epics[1].baseline',
        'epics[1].spec-gate',
        ...storyMembers('epics[1].stories[0]'),
        ...storyMembers('epics[1].stories[1]'),
        'epics[1].gen-e2e',
        'epics[1].retro',
      ],
      { status: 'running', k: 5, n: 14 },
    ),
    group('epics[1].stories[0]', storyMembers('epics[1].stories[0]'), {
      status: 'running',
      k: 1,
      n: 4,
    }),
    group('epics[1].stories[1]', storyMembers('epics[1].stories[1]'), { k: 0, n: 4 }),
    group('epics[2]', ['epics[2].branch', ...storyMembers('epics[2].stories[0]')], { k: 0, n: 5 }),
    group('epics[2].stories[0]', storyMembers('epics[2].stories[0]'), { k: 0, n: 4 }),
  ];

  // The chain `build_run_graph` actually sends: one `seq` edge per consecutive pair. The
  // hierarchy ignores it entirely, and it is here so a test can prove that it does.
  const ids = nodes.map((entry) => entry.id);
  const edges = ids.slice(0, -1).map((from, index) => ({ from, to: ids[index + 1]! }));

  return { nodes, edges, groups };
}

/** The `StepRowOut[]` the Run detail already holds, joined to the graph above by `path`. */
export function twoEpicSteps(): StepRowOut[] {
  return twoEpicGraph().nodes.map((entry, index) => {
    // a row that has not started has no attempt row behind it (`run_views.py:313`)
    const started = entry.status !== 'queued' && entry.status !== 'planned';
    return step(entry.id, {
      seq: index + 1,
      label: entry.label,
      kind: entry.kind,
      status: entry.status ?? 'queued',
      token: entry.token ?? 'QUE',
      attempts: entry.agent && started ? 1 : 0,
      latest:
        entry.agent && started
          ? {
              n: 1,
              harness: 'claude',
              model: 'sonnet',
              seconds: 842,
              exit_code: null,
              cost_usd: null,
              ended_at: null,
              started_at: null,
              log_tail: [],
            }
          : null,
    });
  });
}

/**
 * A `story@1`-shaped plan: bare top-level rows and **no groups**.
 *
 * This is what `story@1`, `task@1` and `repo-init@1` send, and `DiagramSection` mounts for
 * every Run. A fixed four-rank model answered it with an empty EPICS column, `build` drawn
 * under the `EPICS` head and `sync`/`verify`/`commit-guard` nowhere at all.
 */
export function frameLessGraph(overrides: Partial<RunNodeOut> = {}): RunGraphOut {
  const nodes: RunNodeOut[] = [
    node('root', { kind: 'story', label: 'story', status: 'running', token: 'RUN' }),
    node('sync', { label: 'sync', ...DONE }),
    node('build', {
      kind: 'agent',
      gate: 'liveness',
      agent: true,
      label: 'build',
      status: 'running',
      token: 'RUN',
      current: true,
      ...overrides,
    }),
    node('verify', { label: 'verify', ...QUEUED }),
    node('commit-guard', { label: 'commit-guard', ...QUEUED }),
  ];
  const ids = nodes.map((entry) => entry.id);
  return {
    nodes,
    edges: ids.slice(0, -1).map((from, index) => ({ from, to: ids[index + 1]! })),
    groups: [],
  };
}

/** The `StepRowOut[]` joined to `frameLessGraph()` by `path`. */
export function frameLessSteps(overrides: Partial<StepRowOut> = {}): StepRowOut[] {
  return frameLessGraph().nodes.map((entry, index) =>
    step(entry.id, {
      seq: index + 1,
      label: entry.label,
      kind: entry.kind,
      status: entry.status ?? 'queued',
      token: entry.token ?? 'QUE',
      attempts: entry.agent ? 1 : 0,
      latest: entry.agent
        ? {
            n: 1,
            harness: 'claude',
            model: 'sonnet',
            seconds: 842,
            exit_code: null,
            cost_usd: null,
            ended_at: null,
            started_at: null,
            log_tail: [],
          }
        : null,
      ...(entry.agent ? overrides : {}),
    }),
  );
}
