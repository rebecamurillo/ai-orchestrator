/**
 * Guardrail split from `run_order` (epic 2 story 3, EXPERIENCE § 6.3 / § 12 delta 3).
 */
import { describe, expect, it } from 'vitest';
import { MAX_GUARDRAIL_ENTRIES, buildHierarchy } from '../../src/lib/diagram/run-tree';
import { twoEpicGraph, twoEpicSteps } from '../fixtures/run-graph';
import { epicOrderGraph, orderSteps, storyOrderGraph, wideEpicGraph } from '../fixtures/run-order';

const OPEN = new Set(['epics[0]', 'epics[0].stories[0]']);

function strip(graph: ReturnType<typeof storyOrderGraph>, id: string) {
  return buildHierarchy(graph, orderSteps(graph), OPEN).nodes.find((n) => n.id === id)!.guardrail;
}

describe('guardrail split', () => {
  it('splits a story strip around its agent', () => {
    const g = strip(storyOrderGraph(), 'epics[0].stories[0]')!;
    expect(g.before.map((e) => e.label)).toEqual(['sync']);
    expect(g.after.map((e) => e.label)).toEqual(['verify', 'commit', 'push']);
    expect(g.agent).toBe('build');
    expect(g.afterLabel).toBe('AFTER');
    expect(g.overflow).toBe(0);
    expect(g.entries.map((e) => e.label)).toEqual(['sync', 'verify', 'commit', 'push']);
    const push = g.after[2]!;
    expect(push.seq).toBe(5);
    expect(push.n).toBe(3);
    expect(g.before[0]!.n).toBe(0);
  });

  it('splits an epic strip as BEFORE and AFTER STORIES with no agent', () => {
    const g = strip(epicOrderGraph(), 'epics[0]')!;
    expect(g.before.map((e) => e.label)).toEqual(['branch', 'setup', 'baseline']);
    expect(g.after.map((e) => e.label)).toEqual(['commit-e2e', 'e2e', 'push']);
    expect(g.agent).toBeNull();
    expect(g.afterLabel).toBe('AFTER STORIES');
    expect(g.overflow).toBe(0);
  });

  it('joins several agent labels with a triangle', () => {
    const graph = storyOrderGraph();
    graph.nodes.push({ ...graph.nodes[2]!, id: 'epics[0].stories[0].fix', label: 'x · fix' });
    graph.run_order![0]!.rows.splice(2, 0, {
      path: 'epics[0].stories[0].fix',
      phase: 'AGENT',
      label: 'x · fix',
      seq: 9,
      kind: 'agent',
      token: 'QUE',
    });
    expect(strip(graph, 'epics[0].stories[0]')!.agent).toBe('build ▸ fix');
  });

  it('truncates each list on its own and keeps a stop', () => {
    const g = strip(
      wideEpicGraph(MAX_GUARDRAIL_ENTRIES + 3, MAX_GUARDRAIL_ENTRIES + 1),
      'epics[0]',
    )!;
    expect(g.before).toHaveLength(MAX_GUARDRAIL_ENTRIES);
    expect(g.before.some((e) => e.token === 'BLK')).toBe(true);
    expect(g.before.map((e) => e.seq)).toEqual(
      [...g.before.map((e) => e.seq)].sort((a, b) => a - b),
    );
    expect(g.after.map((e) => e.label)).toEqual(['fin']);
    expect(g.overflow).toBe(3);
    expect(g.entries).toHaveLength(MAX_GUARDRAIL_ENTRIES + 1);
  });

  it('falls back to unsplit when an entry has no row in the frame', () => {
    const graph = storyOrderGraph();
    graph.run_order![0]!.rows = graph.run_order![0]!.rows.filter((r) => r.label !== 'push');
    const g = strip(graph, 'epics[0].stories[0]')!;
    expect(g.before).toEqual([]);
    expect(g.after).toEqual([]);
    expect(g.agent).toBeNull();
    expect(g.entries.map((e) => e.label)).toEqual(['sync', 'verify', 'commit', 'push']);
  });

  it('falls back to unsplit when an entry row is marked AGENT, so no stop is hidden', () => {
    const graph = storyOrderGraph();
    const push = graph.run_order![0]!.rows.find((r) => r.label === 'push')!;
    push.phase = 'AGENT';
    const g = strip(graph, 'epics[0].stories[0]')!;
    expect(g.before).toEqual([]);
    expect(g.after).toEqual([]);
    expect(g.entries.map((e) => e.label)).toEqual(['sync', 'verify', 'commit', 'push']);
  });

  it('is unsplit when the graph carries no run_order entry', () => {
    const graph = twoEpicGraph();
    const built = buildHierarchy(
      graph,
      twoEpicSteps(),
      new Set(['epics[0]', 'epics[0].stories[0]']),
    );
    const g = built.nodes.find((n) => n.id === 'epics[0].stories[0]')!.guardrail!;
    expect(g.before).toEqual([]);
    expect(g.after).toEqual([]);
    expect(g.agent).toBeNull();
    expect(g.entries.length).toBeGreaterThan(0);
  });

  it('draws no strip for a card with no deterministic row', () => {
    const graph = storyOrderGraph();
    graph.nodes = graph.nodes.filter((n) => n.agent || n.id === 'root');
    graph.run_order = [];
    const card = buildHierarchy(graph, orderSteps(graph), OPEN).nodes.find(
      (n) => n.id === 'epics[0].stories[0]',
    )!;
    expect(card.guardrail).toBeNull();
  });

  it('uses the order row seq when the node carries none', () => {
    const graph = storyOrderGraph();
    delete graph.nodes[1]!.seq;
    expect(strip(graph, 'epics[0].stories[0]')!.before[0]!.seq).toBe(1);
    const bare = storyOrderGraph();
    delete bare.nodes[1]!.seq;
    bare.run_order = undefined;
    expect(strip(bare, 'epics[0].stories[0]')!.entries[0]!.seq).toBe(0);
  });
});
