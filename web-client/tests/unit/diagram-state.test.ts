/**
 * `src/lib/diagram/diagram-state.ts` — the last-valid rule, as a pure reducer (3.6).
 *
 * The rule the story states: a validation that succeeds swaps the graph and clears the stale
 * line; a validation that fails, and a graph request that fails, leave the graph exactly as
 * it was and set the line. Because the whole previous `Graph` value is retained rather than
 * merged, every node keeps its id — which is what makes "the rendered node ids are exactly
 * the previous graph's" a property of this reducer rather than of the island around it.
 */
import { describe, expect, it } from 'vitest';

import {
  EMPTY_GRAPH,
  STALE_LINE,
  reduceDiagram,
  type DiagramState,
} from '../../src/lib/diagram/diagram-state';
import { EPIC_GRAPH, STORY_GRAPH } from './diagram-fixtures';

const FRESH: DiagramState = { graph: EPIC_GRAPH, stale: false };

describe('reduceDiagram', () => {
  it('swaps the graph and clears the stale line when a validation succeeds', () => {
    const next = reduceDiagram(
      { graph: EPIC_GRAPH, stale: true },
      {
        type: 'validated-ok',
        graph: STORY_GRAPH,
      },
    );

    expect(next).toEqual({ graph: STORY_GRAPH, stale: false });
  });

  it('keeps the previous graph, node for node, when a validation fails', () => {
    const next = reduceDiagram(FRESH, { type: 'validated-failed' });

    expect(next.graph).toBe(EPIC_GRAPH);
    expect(next.graph.nodes.map((entry) => entry.id)).toEqual(
      EPIC_GRAPH.nodes.map((entry) => entry.id),
    );
    expect(next.stale).toBe(true);
  });

  it('keeps the previous graph when the graph request itself fails', () => {
    const next = reduceDiagram(FRESH, { type: 'graph-failed' });

    expect(next.graph).toBe(EPIC_GRAPH);
    expect(next.stale).toBe(true);
  });

  it('never blanks the diagram: a failure after a failure still holds the same graph', () => {
    const once = reduceDiagram(FRESH, { type: 'validated-failed' });
    const twice = reduceDiagram(once, { type: 'graph-failed' });

    expect(twice.graph).toBe(EPIC_GRAPH);
    expect(twice.stale).toBe(true);
  });

  it('clears a stale line a later success replaces, whatever came before it', () => {
    const stale = reduceDiagram(FRESH, { type: 'graph-failed' });

    expect(reduceDiagram(stale, { type: 'validated-ok', graph: EPIC_GRAPH })).toEqual({
      graph: EPIC_GRAPH,
      stale: false,
    });
  });

  it('leaves the state it was given untouched', () => {
    const before = { ...FRESH };

    reduceDiagram(FRESH, { type: 'validated-failed' });

    expect(FRESH).toEqual(before);
  });

  it('states the empty graph and the stale line once, for every reader of them', () => {
    expect(EMPTY_GRAPH).toEqual({ nodes: [], edges: [], groups: [] });
    expect(STALE_LINE).toBe('diagram from last valid version');
  });
});
