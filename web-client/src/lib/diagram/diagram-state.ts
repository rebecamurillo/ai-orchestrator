/**
 * The last-valid rule, as a pure reducer (3.6).
 *
 * The diagram is never blank and never wrong: a validation that succeeds swaps in the graph
 * built from the text that just validated and clears the stale line; a validation that fails,
 * and a graph request that fails, leave the previous graph exactly as it was and say so.
 *
 * The whole previous `Graph` value is retained rather than merged, which is what makes the
 * story's claim — that after an invalid edit the rendered node ids are byte-identical to the
 * previous graph's — a property of this function. Nothing is keyed on array position, and no
 * node's state is carried across by index.
 *
 * A reducer rather than three `setState` calls in the island, because this is the one rule
 * the diagram has, and `vitest.config.ts` runs in `environment: 'node'`: a rule stated here
 * is covered without a DOM.
 */
import type { components } from '../../api/schema';

type Graph = components['schemas']['GraphOut'];

/** What a diagram with nothing to draw holds. Three lists, never `null` (AD-3). */
export const EMPTY_GRAPH: Graph = { nodes: [], edges: [], groups: [] };

/** The line shown beside a diagram that is no longer the text on screen. Stated once. */
export const STALE_LINE = 'diagram from last valid version';

export interface DiagramState {
  graph: Graph;
  /** Whether the drawn graph is older than the editor's current text. */
  stale: boolean;
}

export type DiagramEvent =
  /** The editor's text validated, and this is the graph built from it. */
  | { type: 'validated-ok'; graph: Graph }
  /** The editor's text did not validate, so there is no graph to draw for it. */
  | { type: 'validated-failed' }
  /** The text validated, but the request for its graph did not answer one. */
  | { type: 'graph-failed' };

export function reduceDiagram(state: DiagramState, event: DiagramEvent): DiagramState {
  if (event.type === 'validated-ok') return { graph: event.graph, stale: false };
  return { graph: state.graph, stale: true };
}
