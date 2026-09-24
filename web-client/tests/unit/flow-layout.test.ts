/**
 * `src/lib/diagram/flow-layout.ts` — the hierarchy placed, as the `{nodes, edges}` React
 * Flow renders.
 *
 * Nothing here imports React Flow and nothing here measures a DOM, which is the whole point
 * of the split: the ranked columns, the retry gutter and the handle names are asserted in
 * `environment: 'node'`, where `vitest.config.ts` runs.
 */
import { describe, expect, it } from 'vitest';

import {
  CHIP_GAP,
  CHIP_SIZE,
  chipId,
  EPIC_AGENT_SIZE,
  EPIC_SIZE,
  flowLayout,
  GUTTER_GAP,
  HEAD_HEIGHT,
  MARGIN,
  moreChipId,
  NODE_SEPARATION,
  ROOT_GUARDRAIL_SIZE,
  ROOT_SIZE,
  sizeOf,
  stackVertically,
  STORY_AGENT_SIZE,
  STORY_SIZE,
} from '../../src/lib/diagram/flow-layout';
import { buildHierarchy } from '../../src/lib/diagram/run-tree';
import type { components } from '../../src/api/schema';

type StepRowOut = components['schemas']['StepRowOut'];
import {
  frameLessGraph,
  frameLessSteps,
  group,
  node,
  twoEpicGraph,
  twoEpicSteps,
} from '../fixtures/run-graph';

const OPEN = ['epics[1]', 'epics[1].stories[0]'];

function layout(steps = twoEpicSteps()) {
  return flowLayout(buildHierarchy(twoEpicGraph(), steps, new Set(OPEN)));
}

function placed(id: string) {
  return layout().nodes.find((node) => node.id === id)!;
}

describe('sizeOf', () => {
  it('gives one width per rank, so the four ranks read as four columns', () => {
    const built = buildHierarchy(twoEpicGraph(), twoEpicSteps(), new Set(OPEN));
    const at = (id: string) => sizeOf(built.nodes.find((entry) => entry.id === id)!);

    expect(at('epics[1]')).toEqual(EPIC_SIZE);
    expect(at('epics[1].stories[0]')).toEqual(STORY_SIZE);
    expect(at('epics[1].stories[0].build')).toEqual(STORY_AGENT_SIZE);
  });

  it('grows the root card when it owns a guardrail strip, and not otherwise', () => {
    const owning = buildHierarchy(twoEpicGraph(), [], new Set()).nodes[0]!;
    const bare = buildHierarchy(
      { nodes: [node('root'), node('epics[0].x', { agent: true })], edges: [], groups: [] },
      [],
      new Set(),
    ).nodes[0]!;

    expect(owning.guardrail).not.toBeNull();
    expect(sizeOf(owning)).toEqual(ROOT_GUARDRAIL_SIZE);
    expect(bare.guardrail).toBeNull();
    expect(sizeOf(bare)).toEqual(ROOT_SIZE);
  });

  it('reads an agent card off what holds it, not off its column', () => {
    // ranks collapse, so a frame-less Run's agent sits in column 1 and is still an agent
    // under the root — asking the rank for its width drew it at the story-agent size
    const frameLess = buildHierarchy(frameLessGraph(), frameLessSteps(), new Set());
    const build = frameLess.nodes.find((entry) => entry.id === 'build')!;

    expect(build.rank).toBe(1);
    expect(sizeOf(build)).toEqual(EPIC_AGENT_SIZE);
  });
});

describe('flowLayout — the ranked columns', () => {
  it('is empty for an empty hierarchy rather than a NaN one', () => {
    expect(flowLayout(buildHierarchy({ nodes: [], edges: [], groups: [] }, [], new Set()))).toEqual(
      { nodes: [], edges: [] },
    );
  });

  it('places every card of one rank at the same x', () => {
    const drawn = layout().nodes.filter((node) => node.data.kind === 'card');
    const columns = new Map<string, Set<number>>();
    for (const node of drawn) {
      const rank = String(node.data.kind === 'card' ? node.data.node.rank : 'chip');
      columns.set(rank, (columns.get(rank) ?? new Set()).add(node.position.x));
    }

    expect([...columns.keys()].sort()).toEqual(['0', '1', '2', '3']);
    for (const [rank, xs] of columns) expect([rank, xs.size]).toEqual([rank, 1]);
  });

  it('gives each rank its own x, and every card its own place', () => {
    // dagre writes `x`/`y` into the value object it was handed; handing it the one shared
    // size constant per rank once put every card of a rank on the same point.
    const drawn = layout().nodes.filter((node) => node.data.kind === 'card');
    const seen = new Set(drawn.map((node) => `${node.position.x},${node.position.y}`));

    expect(seen.size).toBe(drawn.length);
    expect(new Set(drawn.map((node) => node.position.x)).size).toBe(4);
  });

  it('stacks siblings down the column in spec order, never in dagre’s', () => {
    // EXPERIENCE-v1 §2.2: siblings stack vertically in spec order. A crossing-minimising
    // ranker is free to answer a crossing-free tree in either direction, and does.
    const order = (ids: string[]) => ids.map((id) => placed(id).position.y);
    const epics = order(['epics[0]', 'epics[1]', 'epics[2]']);
    const rank2 = order([
      'epics[1].spec-gate',
      'epics[1].stories[0]',
      'epics[1].stories[1]',
      'epics[1].gen-e2e',
      'epics[1].retro',
    ]);

    expect([...epics].sort((a, b) => a - b)).toEqual(epics);
    expect([...rank2].sort((a, b) => a - b)).toEqual(rank2);
  });

  it('centres a parent on the span of the children it holds', () => {
    const centre = (id: string) => placed(id).position.y + placed(id).height / 2;

    const first = placed('epics[1].spec-gate');
    const last = placed('epics[1].retro');

    expect(centre('epics[1].stories[0]')).toBeCloseTo(centre('epics[1].stories[0].build'));
    expect(centre('epics[1]')).toBeCloseTo((first.position.y + last.position.y + last.height) / 2);
  });

  it('leaves no two cards of a column overlapping', () => {
    const drawn = layout().nodes.filter((node) => node.data.kind === 'card');
    for (const column of new Set(drawn.map((node) => node.position.x))) {
      const stacked = drawn
        .filter((node) => node.position.x === column)
        .sort((a, b) => a.position.y - b.position.y);
      for (const [index, node] of stacked.slice(1).entries()) {
        const above = stacked[index]!;
        expect(node.position.y).toBeGreaterThanOrEqual(above.position.y + above.height);
      }
    }
  });

  it('gives each card the size its own rank draws at', () => {
    expect([placed('root').width, placed('root').height]).toEqual([
      ROOT_GUARDRAIL_SIZE.width,
      ROOT_GUARDRAIL_SIZE.height,
    ]);
    expect([placed('epics[0]').width, placed('epics[0]').height]).toEqual([
      EPIC_SIZE.width,
      EPIC_SIZE.height,
    ]);
    expect([placed('epics[1].stories[0]').width, placed('epics[1].stories[0]').height]).toEqual([
      STORY_SIZE.width,
      STORY_SIZE.height,
    ]);
  });

  it('orders the columns left to right by rank', () => {
    const x = (id: string) => placed(id).position.x;

    expect(x('root')).toBeLessThan(x('epics[1]'));
    expect(x('epics[1]')).toBeLessThan(x('epics[1].stories[0]'));
    expect(x('epics[1].stories[0]')).toBeLessThan(x('epics[1].stories[0].build'));
  });

  it('gives every card the type its own kind renders with', () => {
    expect(placed('root').type).toBe('runRoot');
    expect(placed('epics[1]').type).toBe('runEpic');
    expect(placed('epics[1].stories[0]').type).toBe('runStory');
    expect(placed('epics[1].stories[0].build').type).toBe('runAgent');
  });

  it('drags every card and chip, but never a head, and connects none of them', () => {
    for (const node of layout().nodes) {
      expect([node.id, node.connectable, node.selectable]).toEqual([node.id, false, false]);
      expect([node.id, node.draggable]).toEqual([node.id, node.data.kind !== 'head']);
    }
  });
});

describe('flowLayout — the connectors', () => {
  it('joins parent to child on the named handles, and nothing else', () => {
    const edges = layout().edges.filter((edge) => edge.className === 'wf-flow-edge');

    expect(edges.length).toBeGreaterThan(0);
    for (const edge of edges) {
      expect(edge.type).toBe('smoothstep');
      expect(edge.sourceHandle).toBe('out');
      expect(edge.targetHandle).toBe('in');
    }
    expect(edges.map((edge) => edge.id)).toContain('epics[1]->epics[1].stories[0]');
  });

  it('never joins two sibling stories', () => {
    const ids = layout().edges.map((edge) => edge.id);

    expect(ids).not.toContain('epics[1].stories[0]->epics[1].stories[1]');
    expect(ids).not.toContain('epics[1].stories[1]->epics[1].stories[0]');
  });
});

describe('flowLayout — the attempts gutter', () => {
  function withAttempts(overrides: Partial<StepRowOut>) {
    return twoEpicSteps().map((row) =>
      row.path === 'epics[1].stories[0].build' ? { ...row, ...overrides } : row,
    );
  }

  function retried() {
    return layout(withAttempts({ attempts: 3 }));
  }

  it('stands every chip in one column right of the widest card', () => {
    const drawn = retried();
    const chips = drawn.nodes.filter((node) => node.type === 'runRetry');
    const widest = Math.max(
      ...drawn.nodes
        .filter((node) => node.data.kind === 'card')
        .map((node) => node.position.x + node.width),
    );

    expect(chips).toHaveLength(2);
    expect(new Set(chips.map((chip) => chip.position.x))).toEqual(new Set([widest + GUTTER_GAP]));
    expect(chips.map((chip) => chip.width)).toEqual([CHIP_SIZE.width, CHIP_SIZE.width]);
  });

  it('moves a second retrying agent’s stack clear of the first', () => {
    // two agents retrying at similar heights share one gutter; each stack only knows its own
    // card, so without a cursor down the gutter the two piles land on top of each other
    const drawn = layout(
      twoEpicSteps().map((row) =>
        row.path === 'epics[1].stories[0].build' || row.path === 'epics[1].spec-gate'
          ? { ...row, attempts: 3, status: 'error' }
          : row,
      ),
    );
    const chips = drawn.nodes
      .filter((chip) => chip.type === 'runRetry')
      .sort((a, b) => a.position.y - b.position.y);

    expect(chips.length).toBeGreaterThan(3);
    for (const [index, chip] of chips.slice(1).entries()) {
      expect(chip.position.y).toBeGreaterThanOrEqual(chips[index]!.position.y + CHIP_SIZE.height);
    }
  });

  it('draws the overflow chip above the stack, where the attempts it stands for happened', () => {
    const drawn = layout(withAttempts({ attempts: 9, status: 'error' })).nodes.filter(
      (node) => node.type === 'runRetry' || node.type === 'runMore',
    );
    const stacked = [...drawn].sort((a, b) => a.position.y - b.position.y);

    expect(stacked[0]!.type).toBe('runMore');
    expect(stacked.slice(1).map((chip) => chip.type)).toEqual([
      'runRetry',
      'runRetry',
      'runRetry',
      'runRetry',
    ]);
  });

  it('caps the gutter with a `+k` chip that loops back like any other', () => {
    const drawn = layout(
      twoEpicSteps().map((row) =>
        row.path === 'epics[1].stories[0].build' ? { ...row, attempts: 9, status: 'error' } : row,
      ),
    );
    const more = drawn.nodes.find((chip) => chip.type === 'runMore')!;

    expect(drawn.nodes.filter((chip) => chip.type === 'runRetry')).toHaveLength(4);
    expect(more.id).toBe(moreChipId({ id: 'epics[1].stories[0].build' }));
    expect(more.data).toEqual({
      kind: 'more',
      overflow: 5,
      ownerPath: 'epics.1.stories.0.build',
    });
    expect(
      drawn.nodes
        .filter((chip) => chip.data.kind === 'chip')
        .map((chip) => (chip.data.kind === 'chip' ? chip.data.chip.n : 0)),
    ).toEqual([6, 7, 8, 9]);
    expect(
      drawn.edges.some(
        (edge) => edge.source === more.id && edge.target === 'epics[1].stories[0].build',
      ),
    ).toBe(true);
  });

  it('stacks the chips on the card’s own centre line', () => {
    const drawn = retried();
    const card = drawn.nodes.find((node) => node.id === 'epics[1].stories[0].build')!;
    const chips = drawn.nodes.filter((node) => node.type === 'runRetry');
    const stack = 2 * CHIP_SIZE.height + CHIP_GAP;

    expect(chips[0]!.position.y).toBeCloseTo(card.position.y + card.height / 2 - stack / 2);
    expect(chips[1]!.position.y - chips[0]!.position.y).toBe(CHIP_SIZE.height + CHIP_GAP);
  });

  it('loops each chip back into the card it retried, dashed and labelled', () => {
    const edges = retried().edges.filter((edge) => edge.className === 'wf-flow-edge-retry');

    expect(edges).toHaveLength(2);
    for (const edge of edges) {
      expect(edge.target).toBe('epics[1].stories[0].build');
      expect(edge.sourceHandle).toBe('back');
      expect(edge.targetHandle).toBe('retry');
      expect(edge.label).toBe('retry');
      expect(edge.markerEnd.color).toBe('var(--color-signal-failed)');
    }
  });

  it('names a chip after the path and the try, so its test id can be read off it', () => {
    const drawn = retried();
    const chip = drawn.nodes.find((node) => node.type === 'runRetry')!;

    expect(chip.id).toBe(chipId({ id: 'epics[1].stories[0].build' }, { n: 1 }));
    expect(chip.data).toEqual({
      kind: 'chip',
      ownerPath: 'epics.1.stories.0.build',
      chip: { n: 1, label: 'try 1', exitCode: null },
    });
  });

  it('opens no gutter at all when nothing retried', () => {
    expect(layout().nodes.some((node) => node.type === 'runRetry')).toBe(false);
    expect(layout().edges.some((edge) => edge.className === 'wf-flow-edge-retry')).toBe(false);
  });
});

describe('stackVertically — when a parent is taller than what it holds', () => {
  /** One epic (102 tall) holding one collapsed story (82): the parent overhangs its subtree. */
  function overhang() {
    return buildHierarchy(
      {
        nodes: [
          node('root'),
          node('epics[0].stories[0].sync', { label: 'epic 1 · story 1-1 · sync' }),
          node('epics[0].stories[0].build', {
            kind: 'agent',
            agent: true,
            label: 'epic 1 · story 1-1 · build',
          }),
        ],
        edges: [],
        groups: [
          group('epics[0]', ['epics[0].stories[0].sync', 'epics[0].stories[0].build']),
          group('epics[0].stories[0]', ['epics[0].stories[0].sync', 'epics[0].stories[0].build']),
        ],
      },
      [],
      // the epic is open so its story is drawn; the story stays closed so the epic holds a
      // subtree exactly one card tall and shorter than itself
      new Set(['epics[0]']),
    );
  }

  it('pushes the subtree down rather than letting the parent reach above it', () => {
    const built = overhang();
    const top = stackVertically(built);
    const height = (id: string) => sizeOf(built.nodes.find((entry) => entry.id === id)!).height;

    // the epic centres on its story; being taller, its own top would land above where the
    // subtree began — so the story moves down and the epic keeps the column's first slot
    expect(top.get('epics[0]')).toBe(MARGIN);
    expect(top.get('epics[0].stories[0]')!).toBeGreaterThan(top.get('epics[0]')!);
    expect(top.get('epics[0].stories[0]')! + height('epics[0].stories[0]')).toBeLessThanOrEqual(
      top.get('epics[0]')! + height('epics[0]'),
    );
  });

  it('still leaves every card of a column clear of its neighbour', () => {
    const built = overhang();
    const top = stackVertically(built);

    for (const rank of built.ranks) {
      const stacked = [...rank].sort((a, b) => top.get(a.id)! - top.get(b.id)!);
      for (const [index, entry] of stacked.slice(1).entries()) {
        const above = stacked[index]!;
        expect(top.get(entry.id)!).toBeGreaterThanOrEqual(
          top.get(above.id)! + sizeOf(above).height,
        );
      }
    }
  });
});

describe('flowLayout — a Run with no frames', () => {
  it('lays two columns out, with the agent right of the root and joined to it', () => {
    const drawn = flowLayout(buildHierarchy(frameLessGraph(), frameLessSteps(), new Set()));
    const root = drawn.nodes.find((entry) => entry.id === 'root')!;
    const build = drawn.nodes.find((entry) => entry.id === 'build')!;

    expect(drawn.nodes.filter((node) => node.data.kind === 'card')).toHaveLength(2);
    expect(build.position.x).toBeGreaterThan(root.position.x + root.width);
    expect(drawn.edges.map((edge) => edge.id)).toEqual(['root->build']);
    // the root holds the strip, so it is drawn at the card size that has room for one
    expect(root.height).toBe(ROOT_GUARDRAIL_SIZE.height);
  });

  it('separates the two cards by no less than the node separation', () => {
    const drawn = flowLayout(buildHierarchy(frameLessGraph(), frameLessSteps(), new Set()));
    const xs = drawn.nodes
      .filter((node) => node.data.kind === 'card')
      .map((entry) => entry.position.x)
      .sort((a, b) => a - b);

    expect(xs[1]! - xs[0]!).toBeGreaterThan(NODE_SEPARATION);
  });
});

describe('flowLayout — a fresh answer every call', () => {
  it('never hands two callers the same empty arrays', () => {
    // these arrays reach `useNodesState`, which owns what it is given; a module-level
    // singleton would have two canvases mutating one list
    const empty = buildHierarchy({ nodes: [], edges: [], groups: [] }, [], new Set());
    const first = flowLayout(empty);
    const second = flowLayout(empty);

    expect(first).toEqual(second);
    expect(first).not.toBe(second);
    expect(first.nodes).not.toBe(second.nodes);
    expect(first.edges).not.toBe(second.edges);
  });
});

describe('flowLayout — the column heads', () => {
  it('emits one head per rank, in rank order, above the cards', () => {
    const drawn = layout();
    const heads = drawn.nodes.filter((node) => node.data.kind === 'head');
    const built = buildHierarchy(twoEpicGraph(), twoEpicSteps(), new Set(OPEN));

    expect(heads.map((head) => (head.data.kind === 'head' ? head.data.label : ''))).toEqual(
      built.heads,
    );
    for (const head of heads) {
      expect(head.position.y).toBe(MARGIN);
      expect(head.height).toBe(HEAD_HEIGHT);
    }
  });

  it('stands each head over the column it names, and clear of every card', () => {
    const drawn = layout();
    const cards = drawn.nodes.filter((node) => node.data.kind === 'card');
    const heads = drawn.nodes.filter((node) => node.data.kind === 'head');

    for (const head of heads) {
      const rank = head.data.kind === 'head' ? head.data.rank : -1;
      const column = cards.filter(
        (card) => card.data.kind === 'card' && card.data.node.rank === rank,
      );
      expect(new Set(column.map((card) => card.position.x))).toEqual(new Set([head.position.x]));
      for (const card of column) {
        expect(card.position.y).toBeGreaterThanOrEqual(head.position.y + HEAD_HEIGHT);
      }
    }
  });

  it('drops a head with its column when the rank collapses', () => {
    const drawn = flowLayout(buildHierarchy(frameLessGraph(), frameLessSteps(), new Set()));
    const heads = drawn.nodes.filter((node) => node.data.kind === 'head');

    expect(heads.map((head) => (head.data.kind === 'head' ? head.data.label : ''))).toEqual([
      'RUN',
      'AGENTS',
    ]);
  });
});
