/**
 * `src/lib/diagram/tree.ts` — the pure tree-synthesis layer for the Run diagram (8.1).
 *
 * `buildRunTree` collapses step-level nodes into story-aggregate nodes; `findCurrentStep`
 * returns the node a Run is currently on. Both are pure and run without a DOM.
 *
 * The fixture is a 2-epic, 4-story graph (2 stories per epic, 2 steps per story) matching
 * the story's own spec: root + plan + 2 epics each with checkout, 2 story groups × 2 steps,
 * push, link.
 */
import { describe, expect, it } from 'vitest';

import type { components } from '../../src/api/schema';
import { buildRunTree, findCurrentStep } from '../../src/lib/diagram/tree';

type RunGraphOut = components['schemas']['RunGraphOut'];
type RunNodeOut = components['schemas']['RunNodeOut'];
type RunGroupOut = components['schemas']['RunGroupOut'];

function runNode(id: string, overrides: Partial<RunNodeOut> = {}): RunNodeOut {
  return {
    id,
    kind: 'shell',
    label: id.split('/').pop()!,
    gate: 'deterministic',
    agent: false,
    human: false,
    call: null,
    status: null,
    token: null,
    current: false,
    ...overrides,
  };
}

function runGroup(
  id: string,
  members: string[],
  overrides: Partial<RunGroupOut> = {},
): RunGroupOut {
  return {
    id,
    kind: 'for_each',
    label: id.split('/').pop()!,
    members,
    status: null,
    ...overrides,
  };
}

/**
 * root + plan + epic-1 (checkout, story-1-1/sync, story-1-1/build, story-1-2/sync,
 * story-1-2/build, push, link) + epic-2 (checkout, story-2-1/sync, story-2-1/build,
 * story-2-2/sync, story-2-2/build, push, link).
 *
 * story-1-1/build is current (BLK), matching the story's AC scenario.
 */
const GRAPH: RunGraphOut = {
  nodes: [
    runNode('root'),
    runNode('plan'),
    runNode('epic-1/checkout'),
    runNode('epic-1/story-1-1/sync', { label: 'sync' }),
    runNode('epic-1/story-1-1/build', {
      label: 'build',
      current: true,
      status: 'blocked',
      token: 'BLK',
    }),
    runNode('epic-1/story-1-2/sync', { label: 'sync' }),
    runNode('epic-1/story-1-2/build', { label: 'build' }),
    runNode('epic-1/push'),
    runNode('epic-1/link'),
    runNode('epic-2/checkout'),
    runNode('epic-2/story-2-1/sync', { label: 'sync' }),
    runNode('epic-2/story-2-1/build', { label: 'build' }),
    runNode('epic-2/story-2-2/sync', { label: 'sync' }),
    runNode('epic-2/story-2-2/build', { label: 'build' }),
    runNode('epic-2/push'),
    runNode('epic-2/link'),
  ],
  edges: [
    { from: 'root', to: 'plan' },
    { from: 'plan', to: 'epic-1/checkout' },
    { from: 'epic-1/checkout', to: 'epic-1/story-1-1/sync' },
    { from: 'epic-1/story-1-1/sync', to: 'epic-1/story-1-1/build' },
    { from: 'epic-1/story-1-1/build', to: 'epic-1/story-1-2/sync' },
    { from: 'epic-1/story-1-2/sync', to: 'epic-1/story-1-2/build' },
    { from: 'epic-1/story-1-2/build', to: 'epic-1/push' },
    { from: 'epic-1/push', to: 'epic-1/link' },
    { from: 'epic-1/link', to: 'epic-2/checkout' },
    { from: 'epic-2/checkout', to: 'epic-2/story-2-1/sync' },
    { from: 'epic-2/story-2-1/sync', to: 'epic-2/story-2-1/build' },
    { from: 'epic-2/story-2-1/build', to: 'epic-2/story-2-2/sync' },
    { from: 'epic-2/story-2-2/sync', to: 'epic-2/story-2-2/build' },
    { from: 'epic-2/story-2-2/build', to: 'epic-2/push' },
    { from: 'epic-2/push', to: 'epic-2/link' },
  ],
  groups: [
    runGroup(
      'epic-1',
      [
        'epic-1/checkout',
        'epic-1/story-1-1/sync',
        'epic-1/story-1-1/build',
        'epic-1/story-1-2/sync',
        'epic-1/story-1-2/build',
        'epic-1/push',
        'epic-1/link',
      ],
      { status: 'DON' },
    ),
    runGroup('epic-2', [
      'epic-2/checkout',
      'epic-2/story-2-1/sync',
      'epic-2/story-2-1/build',
      'epic-2/story-2-2/sync',
      'epic-2/story-2-2/build',
      'epic-2/push',
      'epic-2/link',
    ]),
    runGroup('epic-1/story-1-1', ['epic-1/story-1-1/sync', 'epic-1/story-1-1/build'], {
      status: 'BLK',
    }),
    runGroup('epic-1/story-1-2', ['epic-1/story-1-2/sync', 'epic-1/story-1-2/build']),
    runGroup('epic-2/story-2-1', ['epic-2/story-2-1/sync', 'epic-2/story-2-1/build']),
    runGroup('epic-2/story-2-2', ['epic-2/story-2-2/sync', 'epic-2/story-2-2/build']),
  ],
};

describe('buildRunTree', () => {
  it('synthesises one aggregate node per story group, keyed on the group id', () => {
    const { nodes } = buildRunTree(GRAPH);

    const storyIds = [
      'epic-1/story-1-1',
      'epic-1/story-1-2',
      'epic-2/story-2-1',
      'epic-2/story-2-2',
    ];
    for (const id of storyIds) {
      expect(
        nodes.some((n) => n.id === id),
        id,
      ).toBe(true);
    }
  });

  it('removes original step-level members and keeps epic-level and root nodes', () => {
    const { nodes } = buildRunTree(GRAPH);
    const nodeIds = nodes.map((n) => n.id);

    // Step-level members must be absent
    expect(nodeIds).not.toContain('epic-1/story-1-1/sync');
    expect(nodeIds).not.toContain('epic-1/story-1-1/build');

    // Root, plan, epic-level steps must be present
    expect(nodeIds).toContain('root');
    expect(nodeIds).toContain('plan');
    expect(nodeIds).toContain('epic-1/checkout');
    expect(nodeIds).toContain('epic-1/push');
    expect(nodeIds).toContain('epic-1/link');
  });

  it('sets substeps to the member labels in their declared order', () => {
    const { nodes } = buildRunTree(GRAPH);
    const story11 = nodes.find((n) => n.id === 'epic-1/story-1-1') as RunNodeOut & {
      substeps?: string[];
    };

    expect(story11).toBeDefined();
    expect(story11.substeps).toEqual(['sync', 'build']);
  });

  it('carries the current member token and current=true on the aggregate when any member is current', () => {
    const { nodes } = buildRunTree(GRAPH);
    const story11 = nodes.find((n) => n.id === 'epic-1/story-1-1')!;

    expect(story11.current).toBe(true);
    expect(story11.token).toBe('BLK');
  });

  it('keeps only epic-level groups and removes story-level groups', () => {
    const { groups } = buildRunTree(GRAPH);
    const groupIds = groups.map((g) => g.id);

    expect(groupIds).toContain('epic-1');
    expect(groupIds).toContain('epic-2');
    expect(groupIds).not.toContain('epic-1/story-1-1');
    expect(groupIds).not.toContain('epic-1/story-1-2');
    expect(groupIds).not.toContain('epic-2/story-2-1');
    expect(groupIds).not.toContain('epic-2/story-2-2');
  });

  it('rebuilds edges so the chain passes through story aggregate nodes', () => {
    const { edges } = buildRunTree(GRAPH);

    // epic-1/checkout should connect to epic-1/story-1-1 (first story)
    expect(edges.some((e) => e.from === 'epic-1/checkout' && e.to === 'epic-1/story-1-1')).toBe(
      true,
    );
    // epic-1/story-1-1 should connect to epic-1/story-1-2
    expect(edges.some((e) => e.from === 'epic-1/story-1-1' && e.to === 'epic-1/story-1-2')).toBe(
      true,
    );
    // epic-1/story-1-2 should connect to epic-1/push
    expect(edges.some((e) => e.from === 'epic-1/story-1-2' && e.to === 'epic-1/push')).toBe(true);
  });

  it('produces no duplicate edges', () => {
    const { edges } = buildRunTree(GRAPH);
    const keys = edges.map((e) => `${e.from}->${e.to}`);

    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe('findCurrentStep', () => {
  it('returns the node with current=true', () => {
    const found = findCurrentStep(GRAPH);

    expect(found).not.toBeNull();
    expect(found!.id).toBe('epic-1/story-1-1/build');
    expect(found!.current).toBe(true);
  });

  it('returns null when no node is current', () => {
    const noCurrentGraph: RunGraphOut = {
      ...GRAPH,
      nodes: GRAPH.nodes.map((n) => ({ ...n, current: false })),
    };

    expect(findCurrentStep(noCurrentGraph)).toBeNull();
  });
});
