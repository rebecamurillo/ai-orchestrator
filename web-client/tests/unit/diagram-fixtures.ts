/**
 * The two golden graphs 3.6's browser half is drawn from, exactly as backend-api answers
 * them for the shipped `epic@1` and `story@1` (`backend-api/tests/e2e/test_template_graph.py`
 * pins the same values against the running stack).
 *
 * A fixture rather than a fetch: the diagram modules are pure over `GraphOut`, and what the
 * unit suite proves is that a given graph draws a given picture. That the API really answers
 * this graph is the backend suite's claim, and it is pinned there byte for byte, so the two
 * cannot drift without one of them failing.
 */
import type { components } from '../../src/api/schema';

export type Graph = components['schemas']['GraphOut'];
export type Node = components['schemas']['NodeOut'];

export function node(id: string, overrides: Partial<Node> = {}): Node {
  return {
    id,
    kind: 'shell',
    label: id,
    gate: 'deterministic',
    agent: false,
    human: false,
    call: null,
    ...overrides,
  };
}

/** `epic@1`: steps before and after a loop, a collapsed call, and an item checkpoint. */
export const EPIC_GRAPH: Graph = {
  nodes: [
    node('checkout', { kind: 'git.worktree' }),
    node('baseline', { kind: 'shell' }),
    node('stories.story', {
      kind: 'template',
      label: 'story@1',
      gate: null,
      call: { name: 'story', version: 1 },
    }),
    node('stories.after', {
      kind: 'checkpoint',
      label: 'after',
      gate: 'human',
      human: true,
    }),
    node('push', { kind: 'git.push' }),
    node('link', { kind: 'pr.link', gate: 'liveness' }),
  ],
  edges: [
    { from: 'checkout', to: 'baseline' },
    { from: 'baseline', to: 'stories.story' },
    { from: 'stories.story', to: 'stories.after' },
    { from: 'stories.after', to: 'push' },
    { from: 'push', to: 'link' },
  ],
  groups: [
    {
      id: 'stories',
      label: 'stories',
      kind: 'for_each',
      members: ['stories.story', 'stories.after'],
    },
  ],
};

/** `story@1`: four chained steps, one of which dispatches a harness. */
export const STORY_GRAPH: Graph = {
  nodes: [
    node('sync', { kind: 'git.sync' }),
    node('build', { kind: 'agent', gate: 'liveness', agent: true }),
    node('verify', { kind: 'shell' }),
    node('commit-guard', { kind: 'git.commit' }),
  ],
  edges: [
    { from: 'sync', to: 'build' },
    { from: 'build', to: 'verify' },
    { from: 'verify', to: 'commit-guard' },
  ],
  groups: [],
};

export const EMPTY: Graph = { nodes: [], edges: [], groups: [] };
