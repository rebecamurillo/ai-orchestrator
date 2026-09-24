/**
 * The `RunDetailOut` the diagram's two suites mock `GET /runs/{id}/detail` with.
 *
 * Typed against `components['schemas']`, beside `run-graph.ts`, and for the same reason: the
 * Playwright fixtures were `Record<string, unknown>` and drifted from the contract without a
 * gate noticing. The deleted 8.1 fixture built its `stories` as
 * `{epic_index, story_path, state, seq}` — `StoryCellOut` has no `story_path` and no `seq`,
 * and carries `story_id` — so the Stories strip was being driven by a payload the API cannot
 * send. Types here make that a compile error instead of a screenshot nobody looks at.
 */
import type { components } from '../../src/api/schema';

type RunDetailOut = components['schemas']['RunDetailOut'];
type RunDetailSummaryOut = RunDetailOut['run'];
type StepRowOut = components['schemas']['StepRowOut'];
type StoryCellOut = components['schemas']['StoryCellOut'];

export const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939aa';
/** When the Run entered its current state — the instant the footer's age counts from. */
export const STARTED_AT = '2026-09-07T09:00:00Z';

export function runSummary(overrides: Partial<RunDetailSummaryOut> = {}): RunDetailSummaryOut {
  return {
    id: RUN_ID,
    status: 'running',
    admitted_signals: ['cancel'],
    branch: 'epics/4',
    budget_usd: '15.00',
    compare_urls: [],
    created_at: STARTED_AT,
    inputs: {},
    manual_estimate_h: null,
    plan_ref: null,
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '4.18',
    template: 'initiative',
    terminal_session: false,
    version: 1,
    worktree_path: null,
    worktrees: [],
    accepted_paths: [],
    ...overrides,
  };
}

/** Four stories across two epics — `StoryCellOut`, which is `story_id`, not `story_path`. */
export function stories(): StoryCellOut[] {
  return [
    { epic_index: 0, story_id: '1-1', state: 'done' },
    { epic_index: 0, story_id: '1-2', state: 'done' },
    { epic_index: 1, story_id: '2-1', state: 'active' },
    { epic_index: 1, story_id: '2-2', state: 'pending' },
  ];
}

/** The step rows a fixture already derived, with per-path overrides. */
export function withSteps(
  base: StepRowOut[],
  overrides: Record<string, Partial<StepRowOut>> = {},
): StepRowOut[] {
  return base.map((row) => ({ ...row, ...(overrides[row.path] ?? {}) }));
}

/** Everything `runDetail` will override, with `run` itself overridable field by field. */
export type DetailOverrides = Partial<Omit<RunDetailOut, 'run'>> & {
  run?: Partial<RunDetailSummaryOut>;
};

export function runDetail(steps: StepRowOut[], overrides: DetailOverrides = {}): RunDetailOut {
  return {
    header: {
      meta: {
        project: 'Mixed Signals',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'docs/initiative',
        template: 'initiative',
        version: 1,
        harness: 'claude',
        started_at: STARTED_AT,
        worktree_path: '/work/orchestrator',
      },
    },
    alert: null,
    steps,
    stories: stories(),
    cost: {
      spent_usd: '4.18',
      budget_usd: '15.00',
      tokens_in: 1000,
      tokens_out: 2000,
      wall_clock_seconds: 90,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [
      {
        id: 'g1',
        at: STARTED_AT,
        path: null,
        event: 'start',
        actor: 'machine',
        text: '',
        attempt_n: null,
      },
    ],
    admitted_signals: ['cancel'],
    summary: null,
    ...overrides,
    run: runSummary(overrides.run),
  };
}
