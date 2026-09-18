/**
 * `src/lib/diagram/tree.ts` — expand/collapse behaviour for story groups (story 1-5).
 *
 * `buildRunTree(graph, expandedGroups)` passes members of story groups in `expandedGroups`
 * through as individual nodes instead of synthesising a single aggregate node.
 *
 * Also asserts that `STORY_GROUP_PATTERN` is exported (story 1-5: DiagramSection uses it to
 * compute the initial expansion set).
 *
 * TDD (AD-18): written first — must fail before tree.ts changes.
 */
import { describe, expect, it } from 'vitest';

import type { components } from '../../src/api/schema';
import { buildRunTree, STORY_GROUP_PATTERN } from '../../src/lib/diagram/tree';

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

/** Minimal graph: root + epic-2 (checkout, story-4-1 × 3 steps, push). */
const GRAPH: RunGraphOut = {
  nodes: [
    runNode('root'),
    runNode('epic-2/checkout'),
    runNode('epic-2/story-4-1/sync', { label: 'sync', status: 'done', token: 'DON' }),
    runNode('epic-2/story-4-1/build', {
      label: 'build',
      kind: 'agent',
      agent: true,
      status: 'blocked',
      token: 'BLK',
      current: true,
    }),
    runNode('epic-2/story-4-1/verify', { label: 'verify' }),
    runNode('epic-2/push'),
  ],
  edges: [
    { from: 'root', to: 'epic-2/checkout' },
    { from: 'epic-2/checkout', to: 'epic-2/story-4-1/sync' },
    { from: 'epic-2/story-4-1/sync', to: 'epic-2/story-4-1/build' },
    { from: 'epic-2/story-4-1/build', to: 'epic-2/story-4-1/verify' },
    { from: 'epic-2/story-4-1/verify', to: 'epic-2/push' },
  ],
  groups: [
    runGroup('epic-2', [
      'epic-2/checkout',
      'epic-2/story-4-1/sync',
      'epic-2/story-4-1/build',
      'epic-2/story-4-1/verify',
      'epic-2/push',
    ]),
    runGroup('epic-2/story-4-1', [
      'epic-2/story-4-1/sync',
      'epic-2/story-4-1/build',
      'epic-2/story-4-1/verify',
    ]),
  ],
};

describe('STORY_GROUP_PATTERN export', () => {
  it('is exported from tree.ts', () => {
    expect(STORY_GROUP_PATTERN).toBeDefined();
    expect(STORY_GROUP_PATTERN).toBeInstanceOf(RegExp);
  });

  it('matches story group ids', () => {
    expect(STORY_GROUP_PATTERN.test('epic-2/story-4-1')).toBe(true);
    expect(STORY_GROUP_PATTERN.test('epic-1/story-1-1')).toBe(true);
  });

  it('does not match epic group ids', () => {
    expect(STORY_GROUP_PATTERN.test('epic-2')).toBe(false);
    expect(STORY_GROUP_PATTERN.test('epic-1')).toBe(false);
  });
});

describe('buildRunTree with expandedGroups', () => {
  it('collapses story-4-1 by default (no expandedGroups)', () => {
    const { nodes } = buildRunTree(GRAPH);

    const nodeIds = nodes.map((n) => n.id);
    // aggregate is present
    expect(nodeIds).toContain('epic-2/story-4-1');
    // members are absent
    expect(nodeIds).not.toContain('epic-2/story-4-1/sync');
    expect(nodeIds).not.toContain('epic-2/story-4-1/build');
    expect(nodeIds).not.toContain('epic-2/story-4-1/verify');
  });

  it('collapses story-4-1 when expandedGroups is an empty Set', () => {
    const { nodes } = buildRunTree(GRAPH, new Set());

    const nodeIds = nodes.map((n) => n.id);
    expect(nodeIds).toContain('epic-2/story-4-1');
    expect(nodeIds).not.toContain('epic-2/story-4-1/sync');
  });

  it('expands story-4-1 members when story-4-1 is in expandedGroups', () => {
    const { nodes } = buildRunTree(GRAPH, new Set(['epic-2/story-4-1']));

    const nodeIds = nodes.map((n) => n.id);
    // aggregate is absent
    expect(nodeIds).not.toContain('epic-2/story-4-1');
    // individual members are present
    expect(nodeIds).toContain('epic-2/story-4-1/sync');
    expect(nodeIds).toContain('epic-2/story-4-1/build');
    expect(nodeIds).toContain('epic-2/story-4-1/verify');
  });

  it('keeps edges through individual members when expanded', () => {
    const { edges } = buildRunTree(GRAPH, new Set(['epic-2/story-4-1']));

    // checkout → sync (first member)
    expect(
      edges.some((e) => e.from === 'epic-2/checkout' && e.to === 'epic-2/story-4-1/sync'),
    ).toBe(true);
    // sync → build → verify (internal member chain)
    expect(
      edges.some((e) => e.from === 'epic-2/story-4-1/sync' && e.to === 'epic-2/story-4-1/build'),
    ).toBe(true);
    // verify → push (last member → next node)
    expect(edges.some((e) => e.from === 'epic-2/story-4-1/verify' && e.to === 'epic-2/push')).toBe(
      true,
    );
  });

  it('still keeps epic groups and removes story groups from result', () => {
    const { groups } = buildRunTree(GRAPH, new Set(['epic-2/story-4-1']));

    const groupIds = groups.map((g) => g.id);
    expect(groupIds).toContain('epic-2');
    expect(groupIds).not.toContain('epic-2/story-4-1');
  });
});
