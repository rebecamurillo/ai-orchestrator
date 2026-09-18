/**
 * `src/lib/run/detail.ts` (4.15): every pure derivation the Run detail island and its
 * `src/components/run/*` render from a `RunDetailOut`. This is where the story's real logic
 * lives — `stopKind`/`currentStepPath`/`bannerText`/`stateEnteredAt` all read `gate_record[]`
 * back-to-front the way the module doc explains, since neither `run.park_path` nor a
 * `plan-diff` endpoint is on the wire (the dispatch that started this story: every endpoint
 * the screen consumes already exists, and none may be added).
 */
import { describe, expect, it } from 'vitest';

import {
  bannerLevel,
  bannerText,
  branchLinkHref,
  cancelledAtText,
  crumbText,
  currentStepPath,
  detailRequestPath,
  epicDoneCount,
  hasEffect,
  logTail,
  metaLine,
  moneyRatio,
  runToken,
  stateAgeSeconds,
  stateEnteredAt,
  stepAt,
  stepStatusText,
  stopKind,
  stopSignals,
  storiesByEpic,
  storiesProgressText,
  summaryLine,
  tokensText,
  wallClockText,
  type GateRecordOut,
  type RunDetailOut,
  type StepRowOut,
  type StoryCellOut,
} from '../../src/lib/run/detail';

function gate(overrides: Partial<GateRecordOut> = {}): GateRecordOut {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    at: '2026-09-07T10:00:00Z',
    path: null,
    event: 'start',
    actor: 'machine',
    text: '',
    attempt_n: null,
    ...overrides,
  };
}

function step(overrides: Partial<StepRowOut> = {}): StepRowOut {
  return {
    seq: 1,
    path: 'checkout',
    label: 'checkout',
    kind: 'git.worktree',
    gate: 'deterministic',
    status: 'done',
    token: 'DON',
    reason: null,
    attempts: 1,
    latest: null,
    ...overrides,
  };
}

function story(overrides: Partial<StoryCellOut> = {}): StoryCellOut {
  return { epic_index: 1, story_id: '4-1', state: 'done', ...overrides };
}

function detail(overrides: Partial<RunDetailOut> = {}): RunDetailOut {
  return {
    run: {
      id: '11111111-1111-1111-1111-111111111111',
      status: 'running',
      admitted_signals: ['cancel'],
      branch: 'epics/1',
      budget_usd: '15.00',
      compare_urls: [],
      created_at: '2026-09-07T09:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: '22222222-2222-2222-2222-222222222222',
      repository: '33333333-3333-3333-3333-333333333333',
      spend_usd: '0',
      template: 'initiative',
      terminal_session: false,
      version: 1,
      worktree_path: null,
      worktrees: [],
      accepted_paths: [],
    },
    header: {
      meta: {
        project: 'demo',
        repository: 'demo-repo',
        base_branch: 'main',
        folder: 'docs/initiative',
        template: 'initiative',
        version: 1,
        harness: 'claude',
        started_at: '2026-09-07T09:00:05Z',
        worktree_path: '/work/demo',
      },
    },
    alert: null,
    steps: [],
    stories: [],
    cost: {
      spent_usd: '4.18',
      budget_usd: '15.00',
      tokens_in: 100,
      tokens_out: 200,
      wall_clock_seconds: 90,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: ['cancel'],
    summary: null,
    ...overrides,
  };
}

describe('runToken', () => {
  it('reads the lifecycle table for every status but needs_you', () => {
    expect(runToken(detail({ run: { ...detail().run, status: 'queued' } }).run, null)).toBe('QUE');
    expect(runToken(detail({ run: { ...detail().run, status: 'done' } }).run, null)).toBe('DON');
    expect(runToken(detail({ run: { ...detail().run, status: 'failed' } }).run, null)).toBe('ERR');
    expect(runToken(detail({ run: { ...detail().run, status: 'cancelled' } }).run, null)).toBe(
      'CAN',
    );
  });

  it('is CHK on a checkpoint park and BLK on every other park kind', () => {
    const run = { ...detail().run, status: 'needs_you' as const };
    expect(runToken(run, { token: 'CHK', reason: '', park_kind: 'checkpoint' })).toBe('CHK');
    expect(runToken(run, { token: 'BLK', reason: '', park_kind: 'timeout' })).toBe('BLK');
  });
});

describe('bannerLevel', () => {
  it('is needs-you for BLK/CHK, failed for ERR, null otherwise', () => {
    expect(bannerLevel('BLK')).toBe('needs-you');
    expect(bannerLevel('CHK')).toBe('needs-you');
    expect(bannerLevel('ERR')).toBe('failed');
    expect(bannerLevel('RUN')).toBeNull();
    expect(bannerLevel('DON')).toBeNull();
    expect(bannerLevel('CAN')).toBeNull();
  });
});

describe('currentStepPath / stopKind / bannerText', () => {
  it('reads the parked row off the last gate record matching the park kind', () => {
    const d = detail({
      run: { ...detail().run, status: 'needs_you' },
      alert: { token: 'BLK', reason: 'plan stale: stories.yaml', park_kind: 'plan_stale' },
      gate_record: [
        gate({ event: 'start', path: 'plan', at: '2026-09-07T09:00:00Z' }),
        gate({
          event: 'plan_stale',
          path: 'plan',
          text: 'plan stale: stories.yaml',
          at: '2026-09-07T09:05:00Z',
        }),
      ],
    });

    expect(currentStepPath(d)).toBe('plan');
    expect(stopKind(d, 'BLK')).toBe('plan_stale');
    expect(bannerText(d)).toBe('plan stale: stories.yaml');
  });

  it('reads the failing row off the last failed gate record when the Run is failed', () => {
    const d = detail({
      run: { ...detail().run, status: 'failed' },
      steps: [
        step({
          path: 'build',
          latest: {
            n: 1,
            started_at: null,
            ended_at: null,
            seconds: null,
            harness: null,
            model: null,
            exit_code: 1,
            cost_usd: null,
            log_tail: ['boom'],
          },
        }),
      ],
      gate_record: [gate({ event: 'failed', path: 'build', text: 'exit 1' })],
    });

    expect(currentStepPath(d)).toBe('build');
    expect(stopKind(d, 'ERR')).toBe('failed');
    expect(bannerText(d)).toBe('exit 1');
    expect(logTail(d)).toEqual(['boom']);
  });

  it('reads the running row directly off steps[] while running, and stops nowhere else', () => {
    const d = detail({
      steps: [
        step({ path: 'checkout', status: 'done', token: 'DON' }),
        step({ path: 'build', status: 'running', token: 'RUN' }),
      ],
    });

    expect(currentStepPath(d)).toBe('build');
    expect(stopKind(d, 'RUN')).toBeNull();
    expect(stopKind(d, 'DON')).toBeNull();
    expect(stopKind(d, 'CAN')).toBeNull();
  });
});

describe('cancelledAtText', () => {
  it("names the cancel record's own time", () => {
    const d = detail({
      gate_record: [
        gate({ event: 'cancel', at: '2026-09-07T11:00:00Z', text: 'cancelled by the operator' }),
      ],
    });

    expect(cancelledAtText(d)).toBe('cancelled by operator at 2026-09-07T11:00:00Z');
  });
});

describe('summaryLine', () => {
  it('joins progress, links and skipped ids', () => {
    const d = detail({
      summary: {
        progress: { epics_done: 2, epics_total: 2, stories_done: 8, stories_total: 8, links: 2 },
        links: ['https://a', 'https://b'],
        skipped: ['4-9'],
      },
    });

    expect(summaryLine(d)).toBe('2/2 epics · 8/8 stories · 2 links · skipped: 4-9');
  });

  it('omits the skipped clause when nothing was skipped', () => {
    const d = detail({ summary: { progress: null, links: ['https://a'], skipped: [] } });

    expect(summaryLine(d)).toBe('1 link');
  });
});

describe('money and duration formatting', () => {
  it('prints a ratio, never a percentage', () => {
    expect(moneyRatio(detail().cost)).toBe('$4.18 / $15.00');
  });

  it('prints tokens as in/out', () => {
    expect(tokensText(detail().cost)).toBe('100 in / 200 out');
  });

  it('prints wall-clock as a duration', () => {
    expect(wallClockText(detail().cost)).toBe('1m');
  });
});

describe('hasEffect / stopSignals', () => {
  it('only cancel, retry and continue have any effect this epic', () => {
    expect(hasEffect('cancel')).toBe(true);
    expect(hasEffect('retry')).toBe(true);
    expect(hasEffect('continue')).toBe(true);
    expect(hasEffect('skip_epic')).toBe(false);
    expect(hasEffect('answer')).toBe(false);
  });

  it("excludes cancel from the stop body's own button list", () => {
    expect(stopSignals(['retry', 'cancel', 'skip_epic'])).toEqual(['retry']);
    expect(stopSignals(['continue'])).toEqual(['continue']);
  });
});

describe('storiesByEpic / epicDoneCount / storiesProgressText', () => {
  it('groups by epic_index in first-seen order', () => {
    const stories = [
      story({ epic_index: 2, story_id: '4-2' }),
      story({ epic_index: 1, story_id: '4-1' }),
      story({ epic_index: 2, story_id: '4-3' }),
    ];

    const groups = storiesByEpic(stories);

    expect(groups.map(([index]) => index)).toEqual([2, 1]);
    expect(groups[0]![1].map((c) => c.story_id)).toEqual(['4-2', '4-3']);
  });

  it('counts done cells for one epic', () => {
    expect(epicDoneCount([story({ state: 'done' }), story({ state: 'future' })])).toBe('1/2');
  });

  it('reads epics and stories for an initiative Run', () => {
    const d = detail({
      run: { ...detail().run, template: 'initiative' },
      stories: [
        story({ epic_index: 1, story_id: '4-1', state: 'done' }),
        story({ epic_index: 1, story_id: '4-2', state: 'done' }),
        story({ epic_index: 2, story_id: '4-3', state: 'current' }),
      ],
    });

    expect(storiesProgressText(d)).toBe('1/2 epics · 2/3 stories');
  });

  it('reads only stories for an epic Run (no epic frame of its own)', () => {
    const d = detail({
      run: { ...detail().run, template: 'epic' },
      stories: [story({ state: 'done' })],
    });

    expect(storiesProgressText(d)).toBe('1/1 stories');
  });

  it('is empty with no Story frame at all (repo-init)', () => {
    expect(storiesProgressText(detail({ stories: [] }))).toBe('');
  });
});

describe('stepStatusText', () => {
  it('names the reason on a skipped row', () => {
    expect(
      stepStatusText(step({ status: 'skipped', token: 'SKP', reason: 'no quality_gate_command' })),
    ).toBe('SKP · skipped — no quality_gate_command');
  });

  it('is the plain token otherwise', () => {
    expect(stepStatusText(step({ status: 'done', token: 'DON' }))).toBe('DON');
  });
});

describe('stepAt', () => {
  it('finds the row by path, and is null off no path', () => {
    const steps = [step({ path: 'a' }), step({ path: 'b' })];
    expect(stepAt(steps, 'b')?.path).toBe('b');
    expect(stepAt(steps, null)).toBeNull();
    expect(stepAt(steps, 'missing')).toBeNull();
  });
});

describe('branchLinkHref', () => {
  it('derives a tree link off the first compare URL', () => {
    const d = detail({
      run: {
        ...detail().run,
        branch: 'chore/x',
        compare_urls: ['https://github.com/o/r/compare/main...chore/x'],
      },
    });

    expect(branchLinkHref(d)).toBe('https://github.com/o/r/tree/chore/x');
  });

  it('is null with no compare URL yet', () => {
    expect(branchLinkHref(detail({ run: { ...detail().run, compare_urls: [] } }))).toBeNull();
  });
});

describe('crumbText / metaLine / detailRequestPath', () => {
  it('reads workflows / {branch}', () => {
    expect(crumbText(detail({ run: { ...detail().run, branch: 'epics/1' } }))).toBe(
      'workflows / epics/1',
    );
  });

  it('joins every meta field in the fixed order', () => {
    // Exception-4 revision: model slot inserted between harness and started_at.
    // Authorizing decision: EXPERIENCE-v1.md delta 26 (2026-09-15).
    // Fixture has no `model` in header.meta → '—' placeholder.
    expect(metaLine(detail())).toBe(
      'demo · demo-repo · main · docs/initiative · initiative v1 · claude · — · 2026-09-07T09:00:05Z · /work/demo',
    );
  });

  it('inserts the model value when header.meta.model is set', () => {
    const d = detail({
      header: {
        meta: {
          ...detail().header.meta,
          model: 'claude-opus-5',
        },
      },
    });
    expect(metaLine(d)).toContain('· claude · claude-opus-5 · 2026-09-07T09:00:05Z ·');
  });

  it('is the runs/{id}/detail path', () => {
    expect(detailRequestPath('r1')).toBe('/api/runs/r1/detail');
  });
});

describe('stateEnteredAt / stateAgeSeconds', () => {
  it('reads the park record while parked', () => {
    const d = detail({
      run: { ...detail().run, status: 'needs_you' },
      alert: { token: 'CHK', reason: 'checkpoint', park_kind: 'checkpoint' },
      gate_record: [gate({ event: 'checkpoint', at: '2026-09-07T09:30:00Z' })],
    });

    expect(stateEnteredAt(d)).toBe('2026-09-07T09:30:00Z');
    const now = new Date('2026-09-07T09:31:00Z').getTime();
    expect(stateAgeSeconds(d, now)).toBe(60);
  });

  it('falls back to created_at for a still-queued Run', () => {
    const d = detail({
      run: { ...detail().run, status: 'queued', created_at: '2026-09-07T09:00:00Z' },
    });

    expect(stateEnteredAt(d)).toBe('2026-09-07T09:00:00Z');
  });

  it('never reads negative on clock skew', () => {
    const d = detail({
      run: { ...detail().run, status: 'queued', created_at: '2026-09-07T09:00:00Z' },
    });

    expect(stateAgeSeconds(d, new Date('2026-09-07T08:00:00Z').getTime())).toBe(0);
  });
});
