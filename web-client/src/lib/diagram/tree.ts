/**
 * Collapses a `RunGraphOut`'s step-level nodes into story-aggregate nodes (Epic 8, story 8.1).
 *
 * The raw run graph has one node per step (up to 32+ leaf nodes for a 2-epic 8-story run).
 * The four-column diagram — RUN · EPICS · STORIES · STEPS — shows one box per story group,
 * not one box per step. This module synthesises that view: each story group becomes one node
 * carrying its members' labels as `substeps` and its current member's token as its own.
 *
 * Pure and side-effect-free: the function reads the graph and returns a new set of lists;
 * it never mutates the input. Unit-tested in `tests/unit/run-diagram-tree.test.ts`.
 *
 * **Path invariant** (Block If): story groups have two-segment ids (`epic-\d+/story-[\w-]+`);
 * epic-level steps have one additional segment (`epic-\d+/[^/]+`). If the backend sends a
 * graph where this invariant does not hold, `buildRunTree` will silently include extra nodes
 * rather than crash — the rendering degrades gracefully but the column layout will be wrong.
 */
import type { components } from '../../api/schema';

type RunGraphOut = components['schemas']['RunGraphOut'];
type RunNodeOut = components['schemas']['RunNodeOut'];
type RunGroupOut = components['schemas']['RunGroupOut'];
type EdgeOut = components['schemas']['EdgeOut'];

/** Story group ids match `epic-\d+/story-[\w-]+` (two segments, second starts with `story`). */
export const STORY_GROUP_PATTERN = /^epic-\d+\/story-[\w-]+$/;
/** Epic group ids match `epic-\d+` (one segment). */
const EPIC_GROUP_PATTERN = /^epic-\d+$/;

/**
 * Collapse a full run graph into the four-column tree the diagram renders:
 * - Story groups → one aggregate node per group (with `substeps`)
 * - Epic-level step nodes → kept as-is
 * - Root / top-level nodes → kept as-is
 * - Epic groups → kept; story groups → removed
 * - Edges → rebuilt through the aggregate story nodes, deduplicated
 *
 * Returns `{ nodes, edges, groups }` structurally compatible with `layoutGraph`'s `Graph`
 * parameter — `RunNodeOut` and `RunGroupOut` each carry all fields `NodeOut`/`GroupOut`
 * require, so the caller may pass the result directly (with a cast if the type-checker asks).
 *
 * The synthesised story nodes carry a non-standard `substeps?: string[]` property that
 * `DiagramNode` reads for the sub-step words inside each story box. Nothing else reads it.
 */
export function buildRunTree(
  graph: RunGraphOut,
  expandedGroups: Set<string> = new Set(),
): {
  nodes: RunNodeOut[];
  edges: EdgeOut[];
  groups: RunGroupOut[];
} {
  const storyGroups = graph.groups.filter((g) => STORY_GROUP_PATTERN.test(g.id));
  const epicGroups = graph.groups.filter((g) => EPIC_GROUP_PATTERN.test(g.id));

  // Partition story groups: collapsed → synthesise aggregate; expanded → members pass through
  const collapsedStoryGroups = storyGroups.filter((g) => !expandedGroups.has(g.id));

  // Build a set of all node ids that belong to a COLLAPSED story group
  // (expanded group members pass through as-is, so we do NOT include them here)
  const collapsedMemberIds = new Set<string>();
  for (const group of collapsedStoryGroups) {
    for (const memberId of group.members) {
      collapsedMemberIds.add(memberId);
    }
  }

  // Synthesise one story-level aggregate node per COLLAPSED story group
  const storyNodes: (RunNodeOut & { substeps?: string[] })[] = collapsedStoryGroups.map((group) => {
    const members = group.members
      .map((id) => graph.nodes.find((n) => n.id === id))
      .filter((n): n is RunNodeOut => n !== undefined);

    const currentMember = members.find((m) => m.current);

    // Status: from the current member, else the group's own status token
    const status = currentMember?.status ?? group.status;
    // Token: from the current member, else the group's status (which IS the token for groups)
    const token = currentMember?.token ?? group.status ?? null;
    const current = members.some((m) => m.current);

    // Sub-step words: each member's label (in the order the member list declares them)
    const substeps = members.map((m) => m.label);

    // Label: last segment of the group id, e.g. "epic-1/story-4-1" → "story-4-1"
    const segments = group.id.split('/');
    const label = segments[segments.length - 1] ?? group.id;

    return {
      id: group.id,
      kind: 'story',
      label,
      gate: null,
      agent: false,
      human: false,
      call: null,
      status,
      token,
      current,
      substeps,
    };
  });

  // Keep nodes that are NOT members of any collapsed story group.
  // Members of expanded groups pass through as-is (they are not in collapsedMemberIds).
  const keptNodes = graph.nodes.filter((n) => !collapsedMemberIds.has(n.id));

  // All synthesised nodes: kept (epic/root/expanded-member level) + collapsed aggregates
  const allNodes: RunNodeOut[] = [...keptNodes, ...(storyNodes as RunNodeOut[])];
  const nodeIds = new Set(allNodes.map((n) => n.id));

  // Map from collapsed story member id → story group id for edge substitution
  const memberToGroup = new Map<string, string>();
  for (const group of collapsedStoryGroups) {
    for (const memberId of group.members) {
      memberToGroup.set(memberId, group.id);
    }
  }

  // Rebuild edges: substitute collapsed story member endpoints with the group id, then deduplicate
  const seen = new Set<string>();
  const rebuiltEdges: EdgeOut[] = [];

  for (const edge of graph.edges) {
    const from = memberToGroup.get(edge.from) ?? edge.from;
    const to = memberToGroup.get(edge.to) ?? edge.to;

    if (from === to) continue; // self-edge after substitution (steps within the same story)

    const key = `${from}->${to}`;
    if (seen.has(key)) continue; // deduplicate
    seen.add(key);

    // Only keep edges where both endpoints exist in the rebuilt node set
    if (nodeIds.has(from) && nodeIds.has(to)) {
      rebuiltEdges.push({ from, to });
    }
  }

  return { nodes: allNodes, edges: rebuiltEdges, groups: epicGroups };
}

/**
 * The node the run is currently on — the first one with `current === true` in the flat
 * step list, or `null` when no step is active (e.g. `queued`, `done`, `cancelled`).
 *
 * Searches the original graph's nodes (the step-level list), not the collapsed tree, because
 * `current` is set on individual steps, not story aggregates. The caller uses the returned
 * node's `id` to look up the matching `StepRowOut` for its `seq`.
 */
export function findCurrentStep(graph: RunGraphOut): RunNodeOut | null {
  return graph.nodes.find((n) => n.current) ?? null;
}
