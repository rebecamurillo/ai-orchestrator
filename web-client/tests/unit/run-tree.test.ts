/**
 * `src/lib/diagram/run-tree.ts` — the v3 model: ranks from group-id path prefixes, guardrail
 * strips, derived retry chips, the one-blue-node border rule.
 *
 * Every row of the spec's I/O & Edge-Case Matrix that is answered without a DOM is answered
 * here; the two that are not (a failed `/graph` fetch, a poll tick under a dragged card) are
 * `run-diagram-section.test.ts`'s and the Playwright suite's.
 *
 * The fixtures are the suite's own (`run-tree-fixtures.ts`) and carry the real bracket-index
 * ids — no shipped template is read (hard rule 6).
 */
import { describe, expect, it } from 'vitest';

import {
  borderOf,
  buildHierarchy,
  defaultExpanded,
  durationText,
  failedAttempts,
  findCurrentStep,
  footerText,
  MAX_GUARDRAIL_ENTRIES,
  DOT_GLYPH,
  MAX_RETRY_CHIPS,
  parentOf,
  RANK_HEADS,
  retriesOf,
  ROOT_ID,
  RUN_STATUS_WORD,
  statusWord,
  STEP_STATUS_WORD,
} from '../../src/lib/diagram/run-tree';
import {
  frameLessGraph,
  frameLessSteps,
  group,
  node,
  step,
  twoEpicGraph,
  twoEpicSteps,
} from '../fixtures/run-graph';

function hierarchy(expanded: string[] = ['epics[1]', 'epics[1].stories[0]']) {
  return buildHierarchy(twoEpicGraph(), twoEpicSteps(), new Set(expanded));
}

function byId(id: string) {
  return hierarchy().nodes.find((entry) => entry.id === id);
}

describe('parentOf', () => {
  it('walks a bracket-index path up one segment at a time', () => {
    expect(parentOf('epics[0].stories[3].build')).toBe('epics[0].stories[3]');
    expect(parentOf('epics[0].stories[3]')).toBe('epics[0]');
    expect(parentOf('epics[0]')).toBe(ROOT_ID);
  });

  it('keeps a hyphenated step id whole', () => {
    expect(parentOf('epics[0].stories[1].commit-guard')).toBe('epics[0].stories[1]');
  });
});

describe('buildHierarchy — ranks', () => {
  it('puts the root, the epics, the stories and the story agents in four ranks', () => {
    const built = hierarchy();

    expect(built.ranks[0]!.map((entry) => entry.id)).toEqual([ROOT_ID]);
    expect(built.ranks[1]!.map((entry) => entry.id)).toEqual(['epics[0]', 'epics[1]', 'epics[2]']);
    expect(built.ranks[2]!.map((entry) => entry.id)).toEqual([
      'epics[1].spec-gate',
      'epics[1].stories[0]',
      'epics[1].stories[1]',
      'epics[1].gen-e2e',
      'epics[1].retro',
    ]);
    expect(built.ranks[3]!.map((entry) => entry.id)).toEqual(['epics[1].stories[0].build']);
  });

  it('heads each column with what that column holds', () => {
    expect(hierarchy().heads).toEqual([
      RANK_HEADS.run,
      RANK_HEADS.epics,
      RANK_HEADS.storiesAndAgents,
      RANK_HEADS.agents,
    ]);
  });

  it('interleaves an epic-level agent with its story nodes in plan order', () => {
    const rank2 = hierarchy(['epics[0]']).ranks[2]!.map((entry) => entry.id);

    expect(rank2).toEqual([
      'epics[0].spec-gate',
      'epics[0].stories[0]',
      'epics[0].stories[1]',
      'epics[0].gen-e2e',
      'epics[0].retro',
    ]);
  });

  it('derives the parent chain from id prefixes, not from the graph edges', () => {
    const built = hierarchy();

    expect(byId('epics[1].stories[0].build')!.parentId).toBe('epics[1].stories[0]');
    expect(byId('epics[1].stories[0]')!.parentId).toBe('epics[1]');
    expect(byId('epics[1]')!.parentId).toBe(ROOT_ID);
    // the graph's own edge list is a `seq` chain, and none of it survives into the tree
    expect(built.edges.some((edge) => edge.from === 'plan')).toBe(false);
  });

  it('joins parent rank to child rank only — never two sibling stories', () => {
    const built = hierarchy();
    const rank = new Map(built.nodes.map((entry) => [entry.id, entry.rank]));

    for (const edge of built.edges) {
      expect(rank.get(edge.to)!).toBeGreaterThan(rank.get(edge.from)!);
    }
    expect(built.edges.some((edge) => rank.get(edge.from) === 2 && rank.get(edge.to) === 2)).toBe(
      false,
    );
  });

  it('draws a node only for an agent row, an epic, a story or the root', () => {
    const built = hierarchy();
    const drawn = new Set(built.nodes.map((entry) => entry.id));

    expect(drawn.has('epics[1].stories[0].build')).toBe(true);
    expect(drawn.has('epics[1].stories[0].sync')).toBe(false);
    expect(drawn.has('epics[1].baseline')).toBe(false);
    expect(drawn.has('plan')).toBe(false);
  });

  it('titles a frame from the label segment at its own depth', () => {
    expect(byId('epics[1]')!.title).toBe('epic 2');
    expect(byId('epics[1].stories[0]')!.title).toBe('story 2-1');
    expect(byId('epics[1].stories[0].build')!.title).toBe('build');
  });

  it('states k/n on an epic and the plan size on the root', () => {
    expect(byId('epics[1]')!.meta).toBe('5/14 steps');
    expect(byId(ROOT_ID)!.meta).toBe('3 epics · 5 stories');
  });

  it('states the harness and the model on an agent card, and its duration', () => {
    expect(byId('epics[1].stories[0].build')!.meta).toBe('claude · sonnet');
    expect(byId('epics[1].stories[0].build')!.duration).toBe('14m 02s');
  });

  it('adds the attempt count once the row has more than one', () => {
    const built = buildHierarchy(
      twoEpicGraph(),
      twoEpicSteps().map((row) =>
        row.path === 'epics[1].stories[0].build' ? { ...row, attempts: 3 } : row,
      ),
      new Set(['epics[1]', 'epics[1].stories[0]']),
    );

    expect(built.nodes.find((entry) => entry.id === 'epics[1].stories[0].build')!.meta).toBe(
      'claude · sonnet · 3 attempts',
    );
  });
});

describe('buildHierarchy — expansion', () => {
  it('draws a collapsed epic with no children of its own, and no empty column beside it', () => {
    const built = hierarchy([]);

    expect(built.ranks[1]!.map((entry) => entry.id)).toEqual(['epics[0]', 'epics[1]', 'epics[2]']);
    // every epic closed: the STORIES and AGENTS columns hold nothing, so they are not drawn
    expect(built.ranks).toHaveLength(2);
    expect(built.heads).toEqual([RANK_HEADS.run, RANK_HEADS.epics]);
    expect(built.nodes.find((entry) => entry.id === 'epics[2]')!.meta).toBe('0/5 steps');
  });

  it('gives every epic and story with children a caret, and an agent none', () => {
    expect(byId('epics[1]')!.expandable).toBe(true);
    expect(byId('epics[1].stories[0]')!.expandable).toBe(true);
    expect(byId('epics[1].stories[0].build')!.expandable).toBe(false);
    expect(byId(ROOT_ID)!.expandable).toBe(false);
  });

  it('opens exactly the ancestors of the current step on the first fetch', () => {
    expect([...defaultExpanded(twoEpicGraph())].sort()).toEqual([
      'epics[1]',
      'epics[1].stories[0]',
    ]);
  });

  it('opens nothing when no step is current', () => {
    const graph = twoEpicGraph();
    const quiet = { ...graph, nodes: graph.nodes.map((entry) => ({ ...entry, current: false })) };

    expect(defaultExpanded(quiet).size).toBe(0);
  });

  it('finds the current step, or answers null', () => {
    expect(findCurrentStep(twoEpicGraph())!.id).toBe('epics[1].stories[0].build');
    expect(findCurrentStep({ nodes: [], edges: [], groups: [] })).toBeNull();
  });
});

describe('buildHierarchy — guardrails', () => {
  it('puts a story’s deterministic rows in one strip and emits no node for them', () => {
    const strip = byId('epics[1].stories[0]')!.guardrail!;

    expect(strip.ownerPath).toBe('epics.1.stories.0');
    expect(strip.entries.map((entry) => entry.label)).toEqual(['sync', 'verify', 'commit-guard']);
    expect(strip.overflow).toBe(0);
    expect(strip.entries.map((entry) => entry.stepId)).toEqual(['sync', 'verify', 'commit-guard']);
  });

  it('colours each dot by the row’s own state, running included', () => {
    const strip = byId('epics[1].stories[0]')!.guardrail!;

    expect(strip.entries.map((entry) => entry.dot)).toEqual(['done', 'queued', 'queued']);
    expect(strip.muted).toBe(false);
  });

  it('mutes a strip whose every row is still queued', () => {
    expect(byId('epics[1].stories[1]')!.guardrail!.muted).toBe(true);
  });

  it('draws four entries then `+k` on a frame with more than four', () => {
    const members = Array.from({ length: 8 }, (_, index) => `epics[0].g${index}`);
    const built = buildHierarchy(
      {
        nodes: [node('root', { kind: 'epic' }), ...members.map((id) => node(id))],
        edges: [],
        groups: [group('epics[0]', members)],
      },
      [],
      new Set(),
    );
    const strip = built.nodes.find((entry) => entry.id === 'epics[0]')!.guardrail!;

    expect(strip.entries).toHaveLength(MAX_GUARDRAIL_ENTRIES);
    expect(strip.overflow).toBe(4);
  });

  it('collects every strip it drew', () => {
    const built = hierarchy();

    expect(built.guardrails.map((strip) => strip.ownerId)).toContain('epics[1].stories[0]');
    expect(built.guardrails.every((strip) => strip.entries.length > 0)).toBe(true);
  });
});

describe('failed attempts and their chips', () => {
  it('counts the in-flight attempt of a running row as not-yet-failed', () => {
    // the frozen matrix: `attempts: 3`, `running` → two chips
    expect(failedAttempts({ attempts: 3, status: 'running' })).toBe(2);
    expect(
      retriesOf(step('p', { attempts: 3, status: 'running' })).chips.map((c) => c.label),
    ).toEqual(['try 1', 'try 2']);
  });

  it('derives one failure from a row that ended done after two attempts', () => {
    expect(retriesOf(step('p', { attempts: 2, status: 'done' })).chips).toHaveLength(1);
  });

  it('draws no chip and no gutter for a single-attempt done row', () => {
    expect(retriesOf(step('p', { attempts: 1, status: 'done' })).chips).toEqual([]);
  });

  it('counts every attempt of a row the agent could not finish', () => {
    expect(failedAttempts({ attempts: 2, status: 'error' })).toBe(2);
    expect(failedAttempts({ attempts: 1, status: 'blocked' })).toBe(1);
  });

  it('draws two chips for a blocked park — the agent handed back unable to finish', () => {
    expect(retriesOf(step('p', { attempts: 2, status: 'blocked' })).chips.map((c) => c.n)).toEqual([
      1, 2,
    ]);
  });

  it('draws one chip for a checkpoint park — the designed stop is not a failure', () => {
    // operator correction, 2026-09-24: `checkpoint` used to count as a failed newest attempt,
    // so a run merely waiting at a checkpoint painted a red `failed` chip it never earned
    expect(failedAttempts({ attempts: 2, status: 'checkpoint' })).toBe(1);
    expect(retriesOf(step('p', { attempts: 2, status: 'checkpoint' })).chips).toHaveLength(1);
  });

  it('states no exit code on a checkpoint park, whatever the latest attempt carries', () => {
    const { chips } = retriesOf(
      step('p', {
        attempts: 2,
        status: 'checkpoint',
        latest: {
          n: 2,
          harness: 'claude',
          model: 'sonnet',
          seconds: 12,
          exit_code: 0,
          cost_usd: null,
          ended_at: null,
          started_at: null,
          log_tail: [],
        },
      }),
    );

    expect(chips.map((chip) => chip.exitCode)).toEqual([null]);
  });

  it('caps the gutter at the NEWEST failures, and counts the rest', () => {
    // keeping the first four threw away the only chip that can state an exit code — the
    // wire carries one attempt's, the latest, and it is always the last chip
    const { chips, overflow } = retriesOf(
      step('p', {
        attempts: 9,
        status: 'error',
        latest: {
          n: 9,
          harness: 'claude',
          model: 'sonnet',
          seconds: 12,
          exit_code: 1,
          cost_usd: null,
          ended_at: null,
          started_at: null,
          log_tail: [],
        },
      }),
    );

    expect(chips).toHaveLength(MAX_RETRY_CHIPS);
    expect(chips.map((chip) => chip.n)).toEqual([6, 7, 8, 9]);
    expect(chips.map((chip) => chip.label)).toEqual(['try 6', 'try 7', 'try 8', 'try 9']);
    expect(chips.map((chip) => chip.exitCode)).toEqual([null, null, null, 1]);
    expect(overflow).toBe(5);
  });

  it('states an exit code on the latest failed chip only', () => {
    const { chips } = retriesOf(
      step('p', {
        attempts: 2,
        status: 'error',
        latest: {
          n: 2,
          harness: 'claude',
          model: 'sonnet',
          seconds: 12,
          exit_code: 1,
          cost_usd: null,
          ended_at: null,
          started_at: null,
          log_tail: [],
        },
      }),
    );

    expect(chips.map((chip) => chip.exitCode)).toEqual([null, 1]);
  });

  it('never repeats a succeeded attempt’s exit code on a failed chip', () => {
    const { chips } = retriesOf(
      step('p', {
        attempts: 2,
        status: 'done',
        latest: {
          n: 2,
          harness: 'claude',
          model: 'sonnet',
          seconds: 12,
          exit_code: 0,
          cost_usd: null,
          ended_at: null,
          started_at: null,
          log_tail: [],
        },
      }),
    );

    expect(chips.map((chip) => chip.exitCode)).toEqual([null]);
  });

  it('answers nothing at all for a row the detail never carried', () => {
    expect(retriesOf(undefined)).toEqual({ chips: [], overflow: 0 });
  });

  it('hangs the chips off the agent node that retried', () => {
    const steps = twoEpicSteps().map((row) =>
      row.path === 'epics[1].stories[0].build' ? { ...row, attempts: 3 } : row,
    );
    const built = buildHierarchy(
      twoEpicGraph(),
      steps,
      new Set(['epics[1]', 'epics[1].stories[0]']),
    );

    expect(built.retries).toEqual([
      {
        nodeId: 'epics[1].stories[0].build',
        overflow: 0,
        chips: [
          { n: 1, label: 'try 1', exitCode: null },
          { n: 2, label: 'try 2', exitCode: null },
        ],
      },
    ]);
  });
});

describe('the unjoinable node', () => {
  it('renders off the graph alone, with no attempts and no CTA target', () => {
    const built = buildHierarchy(twoEpicGraph(), [], new Set(['epics[1]', 'epics[1].stories[0]']));
    const orphan = built.nodes.find((entry) => entry.id === 'epics[1].stories[0].build')!;

    expect(orphan.token).toBe('RUN');
    expect(orphan.joined).toBe(false);
    expect(orphan.retries).toEqual([]);
    expect(orphan.meta).toBe('');
    expect(orphan.duration).toBe('—');
  });
});

describe('the empty plan', () => {
  it('answers no rank, no head and no edge', () => {
    const built = buildHierarchy({ nodes: [], edges: [], groups: [] }, [], new Set());

    expect(built.nodes).toEqual([]);
    expect(built.edges).toEqual([]);
    expect(built.ranks).toEqual([]);
    expect(built.heads).toEqual([]);
  });
});

describe('borderOf — one blue node, and the ancestors that hold it', () => {
  it('gives the blue border to the current step alone', () => {
    expect(borderOf('RUN', true)).toBe('running');
    expect(borderOf('RUN', false)).toBe('inflight');
  });

  it('keeps a stop coloured at every level', () => {
    expect(borderOf('BLK', false)).toBe('blocked');
    expect(borderOf('CHK', false)).toBe('checkpoint');
    expect(borderOf('ERR', false)).toBe('error');
  });

  it('never makes a skipped or cancelled node green', () => {
    expect(borderOf('SKP', false)).toBe('skipped');
    expect(borderOf('CAN', false)).toBe('cancelled');
    expect(borderOf('DON', false)).toBe('done');
  });

  it('draws no border at all for a group a cancelled Run never reached', () => {
    expect(borderOf(null, false)).toBe('none');
  });

  it('states nothing rather than a confident grey for a token it does not know', () => {
    // AD-8: the UI renders the tokens the writers stored. Painting an unknown value
    // `queued` would read as a fact about the run rather than as the contract drift it is.
    expect(borderOf('ZZZ', false)).toBe('none');
  });

  it('gives an unrecognised status word no token at all', () => {
    const built = buildHierarchy(
      {
        nodes: [node('root'), node('epics[0].x')],
        edges: [],
        groups: [group('epics[0]', ['epics[0].x'], { status: 'spelunking' })],
      },
      [],
      new Set(),
    );
    const epic = built.nodes.find((entry) => entry.id === 'epics[0]')!;

    expect(epic.token).toBeNull();
    expect(epic.border).toBe('none');
  });

  it('applies the rule through the whole tree', () => {
    expect(byId(ROOT_ID)!.border).toBe('inflight');
    expect(byId('epics[1]')!.border).toBe('inflight');
    expect(byId('epics[1].stories[0]')!.border).toBe('inflight');
    expect(byId('epics[1].stories[0].build')!.border).toBe('running');
    expect(byId('epics[1]')!.token).toBe('RUN');
  });

  it('reads a group whose status the backend sent as a token', () => {
    const built = buildHierarchy(
      {
        nodes: [node('root'), node('epics[0].x')],
        edges: [],
        groups: [group('epics[0]', ['epics[0].x'], { status: 'DON' })],
      },
      [],
      new Set(),
    );

    expect(built.nodes.find((entry) => entry.id === 'epics[0]')!.token).toBe('DON');
  });

  it('leaves a cancelled Run’s groups tokenless', () => {
    const built = buildHierarchy(
      {
        nodes: [node('root', { status: 'cancelled', token: 'CAN' }), node('epics[0].x')],
        edges: [],
        groups: [group('epics[0]', ['epics[0].x'], { status: null })],
      },
      [],
      new Set(),
    );

    expect(built.nodes.find((entry) => entry.id === 'epics[0]')!.token).toBeNull();
    expect(built.nodes.find((entry) => entry.id === 'root')!.token).toBe('CAN');
  });
});

describe('durationText', () => {
  it('reads minutes and seconds, then hours and minutes', () => {
    expect(durationText(1127)).toBe('18m 47s');
    expect(durationText(3840)).toBe('1h 04m');
    expect(durationText(0)).toBe('00m 00s');
  });

  it('is an em dash when the wire carries none', () => {
    expect(durationText(null)).toBe('—');
    expect(durationText(undefined)).toBe('—');
  });
});

describe('footerText', () => {
  it('names the step by its label, the way a single-line context must', () => {
    expect(
      footerText(
        { seq: 25, label: 'epic 2 · story 2-1 · build' },
        { steps: 49, storiesDone: 2, stories: 4 },
        { word: 'running', age: '00h 42m' },
      ),
    ).toBe('step 25 of 49 · epic 2 · story 2-1 · build · running 00h 42m · 2/4 stories');
  });

  it('says only what it knows when nothing is current', () => {
    expect(
      footerText(null, { steps: 49, storiesDone: 4, stories: 4 }, { word: 'done', age: '2m' }),
    ).toBe('4/4 stories');
  });
});

describe('an epic Run, whose plan has no epics[i] frame', () => {
  it('hangs its stories and their agents off the root, in two columns, not four', () => {
    const built = buildHierarchy(
      {
        nodes: [
          node('root', { kind: 'epic', label: 'epic' }),
          node('stories[0].sync', { label: 'story 1-1 · sync' }),
          node('stories[0].build', {
            kind: 'agent',
            agent: true,
            label: 'story 1-1 · build',
          }),
        ],
        edges: [],
        groups: [group('stories[0]', ['stories[0].sync', 'stories[0].build'])],
      },
      [],
      new Set(['stories[0]']),
    );

    // the EPICS column holds nothing, so it is not drawn and its head is not printed
    expect(built.heads).toEqual([RANK_HEADS.run, RANK_HEADS.stories, RANK_HEADS.agents]);
    expect(built.nodes.find((entry) => entry.id === 'stories[0]')!.rank).toBe(1);
    expect(built.nodes.find((entry) => entry.id === 'stories[0]')!.title).toBe('story 1-1');
    expect(built.nodes.find((entry) => entry.id === 'stories[0].build')!.rank).toBe(2);
    expect(built.nodes.find((entry) => entry.id === 'root')!.meta).toBe('1 story');
  });
});

describe('a Run with no frames at all (story@1, task@1, repo-init@1)', () => {
  function frameLess() {
    return buildHierarchy(frameLessGraph(), frameLessSteps(), new Set());
  }

  it('draws two columns, headed RUN and AGENTS', () => {
    const built = frameLess();

    expect(built.ranks.map((rank) => rank.map((entry) => entry.id))).toEqual([
      [ROOT_ID],
      ['build'],
    ]);
    expect(built.heads).toEqual([RANK_HEADS.run, RANK_HEADS.agents]);
  });

  it('puts the agent one rank right of the root, not under an EPICS head', () => {
    const build = frameLess().nodes.find((entry) => entry.id === 'build')!;

    expect(build.rank).toBe(1);
    expect(build.parentId).toBe(ROOT_ID);
    expect(build.parentKind).toBe('root');
    expect(frameLess().edges).toEqual([{ id: 'root->build', from: ROOT_ID, to: 'build' }]);
  });

  it('shows its deterministic rows on the root card rather than nowhere', () => {
    const strip = frameLess().nodes.find((entry) => entry.id === ROOT_ID)!.guardrail!;

    expect(strip.ownerId).toBe(ROOT_ID);
    expect(strip.entries.map((entry) => entry.label)).toEqual(['sync', 'verify', 'commit-guard']);
    expect(strip.entries.map((entry) => entry.dot)).toEqual(['done', 'queued', 'queued']);
  });

  it('states its size rather than two absences', () => {
    // `0 epics · 0 stories` states what the Run has none of and nothing about what it has
    expect(frameLess().nodes.find((entry) => entry.id === ROOT_ID)!.meta).toBe('4 steps');
  });
});

describe('root-owned rows', () => {
  it('puts a plan row that sits outside every frame on the root card', () => {
    const strip = hierarchy().nodes.find((entry) => entry.id === ROOT_ID)!.guardrail!;

    expect(strip.entries.map((entry) => entry.stepId)).toContain('plan');
    expect(strip.ownerPath).toBe(ROOT_ID);
  });

  it('collects a strip only for an owner that has a card to draw it on', () => {
    // the build-implies-draw invariant: `root`, `epic` and `story` each render a
    // `<GuardrailStrip>`; an `agent` card has no strip, so it must never collect entries
    const owners = new Map(hierarchy().nodes.map((entry) => [entry.id, entry.kind]));

    for (const strip of hierarchy().guardrails) {
      expect([strip.ownerId, owners.get(strip.ownerId)]).not.toEqual([strip.ownerId, 'agent']);
      expect(owners.get(strip.ownerId)).toBeDefined();
    }
  });
});

describe('a truncated strip never hides a stop', () => {
  function stripOfEight(blockedAt: number) {
    const members = Array.from({ length: 8 }, (_, index) => `epics[0].g${index}`);
    const built = buildHierarchy(
      {
        nodes: [
          node('root'),
          ...members.map((id, index) =>
            node(id, index === blockedAt ? { status: 'blocked', token: 'BLK' } : {}),
          ),
        ],
        edges: [],
        groups: [group('epics[0]', members)],
      },
      [],
      new Set(),
    );
    return built.nodes.find((entry) => entry.id === 'epics[0]')!.guardrail!;
  }

  it('keeps a blocked sixth row among the four shown, with `+4` for the rest', () => {
    const strip = stripOfEight(5);

    expect(strip.entries).toHaveLength(MAX_GUARDRAIL_ENTRIES);
    expect(strip.entries.map((entry) => entry.stepId)).toContain('g5');
    expect(strip.overflow).toBe(4);
  });

  it('leaves the visible entries in plan order, stop included', () => {
    const shown = stripOfEight(5).entries.map((entry) => entry.stepId);

    expect(shown).toEqual([...shown].sort());
    expect(shown).toEqual(['g0', 'g1', 'g2', 'g5']);
  });

  it('changes nothing when every row is settled', () => {
    expect(stripOfEight(-1).entries.map((entry) => entry.stepId)).toEqual(['g0', 'g1', 'g2', 'g3']);
  });
});

describe('the two status-word maps', () => {
  it('agree everywhere but on ERR, which the spine reads twice', () => {
    // EXPERIENCE-v1 *State vocabulary*: a Run is `failed`, a row is `error`. One module owns
    // both, because two copies of this table had already drifted at exactly this token.
    const differing = Object.keys(RUN_STATUS_WORD).filter(
      (token) => RUN_STATUS_WORD[token] !== STEP_STATUS_WORD[token],
    );

    expect(differing).toEqual(['ERR']);
    expect([RUN_STATUS_WORD.ERR, STEP_STATUS_WORD.ERR]).toEqual(['failed', 'error']);
  });

  it('spells every token the diagram can show', () => {
    const vocabulary = ['BLK', 'CAN', 'CHK', 'DON', 'ERR', 'QUE', 'RUN', 'SKP'];

    expect(Object.keys(RUN_STATUS_WORD).sort()).toEqual(vocabulary);
    expect(Object.keys(STEP_STATUS_WORD).sort()).toEqual(vocabulary);
    expect(STEP_STATUS_WORD.SKP).toBe('skipped');
  });
});

describe('a frame nested under another loop', () => {
  /** `repos[0].epics[1]` — a multi-repo initiative; `_group_prefixes` writes the whole prefix. */
  function nested() {
    const members = [
      'repos[0].epics[1].branch',
      'repos[0].epics[1].stories[0].sync',
      'repos[0].epics[1].stories[0].build',
    ];
    return buildHierarchy(
      {
        nodes: [
          node('root', { kind: 'initiative', label: 'initiative' }),
          node(members[0]!, { label: 'repos 1 · epic 2 · branch' }),
          node(members[1]!, { label: 'repos 1 · epic 2 · story 2-1 · sync' }),
          node(members[2]!, {
            kind: 'agent',
            agent: true,
            label: 'repos 1 · epic 2 · story 2-1 · build',
          }),
        ],
        edges: [],
        groups: [
          group('repos[0].epics[1]', members),
          group('repos[0].epics[1].stories[0]', members.slice(1)),
        ],
      },
      [],
      new Set(['repos[0].epics[1]', 'repos[0].epics[1].stories[0]']),
    );
  }

  it('reads an epic frame that is not top-level as an epic', () => {
    // anchoring the epic pattern at the start (and not the story one) made this id match
    // neither, and its whole subtree re-parented to the root
    const built = nested();
    const epic = built.nodes.find((entry) => entry.id === 'repos[0].epics[1]')!;

    expect(epic.kind).toBe('epic');
    expect(epic.rank).toBe(1);
    expect(epic.parentId).toBe(ROOT_ID);
    expect(epic.title).toBe('epic 2');
  });

  it('hangs its story and that story’s agent under it, in four columns', () => {
    const built = nested();

    expect(built.heads).toEqual([
      RANK_HEADS.run,
      RANK_HEADS.epics,
      RANK_HEADS.stories,
      RANK_HEADS.agents,
    ]);
    expect(built.nodes.find((entry) => entry.id === 'repos[0].epics[1].stories[0]')!.parentId).toBe(
      'repos[0].epics[1]',
    );
    expect(
      built.nodes.find((entry) => entry.id === 'repos[0].epics[1].stories[0].build')!.parentId,
    ).toBe('repos[0].epics[1].stories[0]');
  });

  it('keeps each frame’s own guardrail row on the frame that owns it', () => {
    const built = nested();
    const epic = built.nodes.find((entry) => entry.id === 'repos[0].epics[1]')!;
    const story = built.nodes.find((entry) => entry.id === 'repos[0].epics[1].stories[0]')!;

    expect(epic.guardrail!.entries.map((entry) => entry.stepId)).toEqual(['branch']);
    expect(story.guardrail!.entries.map((entry) => entry.stepId)).toEqual(['sync']);
    expect(built.nodes.find((entry) => entry.id === ROOT_ID)!.guardrail).toBeNull();
  });
});

describe('a graph that names no root node', () => {
  function rootless() {
    return buildHierarchy(
      {
        nodes: [
          node('sync', { label: 'sync' }),
          node('build', { kind: 'agent', agent: true, label: 'build' }),
        ],
        edges: [],
        groups: [],
      },
      [],
      new Set(),
    );
  }

  it('still draws a root card, so its frame-less rows have an owner', () => {
    // the guardrail loop drops an entry whose owner does not exist: without a root card,
    // `sync` was collected and then silently discarded
    const built = rootless();
    const root = built.nodes.find((entry) => entry.id === ROOT_ID)!;

    expect(root.kind).toBe('root');
    expect(root.guardrail!.entries.map((entry) => entry.stepId)).toEqual(['sync']);
  });

  it('states the plan size without over- or under-counting its own card', () => {
    expect(rootless().nodes.find((entry) => entry.id === ROOT_ID)!.meta).toBe('2 steps');
  });

  it('claims no state it was not told', () => {
    const root = rootless().nodes.find((entry) => entry.id === ROOT_ID)!;

    expect(root.token).toBeNull();
    expect(root.border).toBe('none');
    expect(root.title).toBe('run');
  });

  it('builds no strip at all for a graph with no rows', () => {
    const empty = buildHierarchy({ nodes: [], edges: [], groups: [] }, [], new Set());

    expect(empty.nodes).toEqual([]);
    expect(empty.guardrails).toEqual([]);
  });
});

describe('the guardrail dot is a shape as well as a hue', () => {
  it('gives every state a glyph of its own', () => {
    const glyphs = Object.values(DOT_GLYPH);

    // `running` and `inflight` deliberately share one: a guardrail row is never the current
    // step, so the pair can never appear in one strip
    expect(new Set(glyphs).size).toBe(glyphs.length - 2);
    expect(DOT_GLYPH.done).not.toBe(DOT_GLYPH.queued);
    expect(DOT_GLYPH.skipped).toBe(DOT_GLYPH.cancelled);
  });

  it('covers every state a strip entry can carry', () => {
    const dots = new Set(
      hierarchy().guardrails.flatMap((strip) => strip.entries.map((entry) => entry.dot)),
    );

    for (const dot of dots) expect(DOT_GLYPH[dot]).toBeTruthy();
  });
});

describe('statusWord', () => {
  it('is the one answer all three readers give', () => {
    expect(statusWord('DON')).toBe('done');
    expect(statusWord('ERR')).toBe('error');
    expect(statusWord(null)).toBe('no status');
  });

  it('prints a token it does not know verbatim rather than inventing a word for it', () => {
    expect(statusWord('ZZZ')).toBe('ZZZ');
  });

  it('is what a strip entry says', () => {
    const strip = byId('epics[1].stories[0]')!.guardrail!;

    expect(strip.entries.map((entry) => entry.word)).toEqual(['done', 'queued', 'queued']);
  });
});
