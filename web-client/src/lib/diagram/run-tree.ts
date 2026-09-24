/**
 * The v3 run-diagram model: a ranked-column hierarchy derived from group-id path prefixes
 * (EXPERIENCE-v1 §2.2 *The diagram*, 2026-09-24; artboard `mockups/RunDiagram-v3.html`).
 *
 * This module replaces `diagram/tree.ts`, whose `STORY_GROUP_PATTERN` (`^epic-\d+\/story-…$`)
 * could never match the bracket-index ids the backend actually emits (`epics[0].stories[3]`,
 * `application/graph.py::_group_prefixes`), so no story ever collapsed and every row landed
 * in one dagre rank. Nothing here matches a slugged id: a parent is a **path prefix**.
 *
 *     epics[0].stories[3].build → epics[0].stories[3] → epics[0] → root
 *
 * **The graph's `edges` are ignored.** `build_run_graph` chains every row in `seq` order
 * (`graph.py::_chain`), which is a statement about execution order, not about structure;
 * the v3 layout states hierarchy and there are no sibling-to-sibling edges to draw.
 *
 * **What is a node.** Only `RunNodeOut.agent === true` rows, plus the run root, one node per
 * `epics[i]` group and one per `…stories[j]` group. Everything else — deterministic rows and
 * `checkpoint` rows alike — becomes a guardrail-strip entry on the epic, story **or root**
 * that owns it. The STEPS tab keeps every planned row; the diagram narrows what it *draws*.
 *
 * **Ranks collapse to what exists** *(operator amendment, 2026-09-24)*. `DiagramSection`
 * mounts for every Run, and `story@1`, `task@1` and `repo-init@1` plan bare top-level rows
 * with no `epics[i]`/`stories[j]` frame at all. A fixed four-rank model answered those with
 * an empty EPICS column, an agent card drawn under the `EPICS` head and every deterministic
 * row invisible. So an empty rank is dropped, the surviving columns are renumbered, and
 * `heads` is computed from what each column actually holds — a frame-less Run reads
 * `RUN · AGENTS`, and its deterministic rows sit on the root card's guardrail strip.
 *
 * **Failure data is a client-side join** on `path` against the `RunDetailOut.steps[]` the
 * Run detail already polls — this story adds no field to `RunNodeOut` and no backend call.
 *
 * Pure and DOM-free: no React, no React Flow, no dagre. Unit-tested under
 * `environment: 'node'` in `tests/unit/run-tree.test.ts`.
 */
import type { components } from '../../api/schema';
import { encode } from '../step-path';

type RunGraphOut = components['schemas']['RunGraphOut'];
type RunNodeOut = components['schemas']['RunNodeOut'];
type RunGroupOut = components['schemas']['RunGroupOut'];
type StepRowOut = components['schemas']['StepRowOut'];

/** The synthetic node standing for the Run itself (`application/graph.py::ROOT_ID`). */
export const ROOT_ID = 'root';

/** Guardrail entries drawn before the `+k` overflow (I/O matrix: 8 members → 4 then `+4`). */
export const MAX_GUARDRAIL_ENTRIES = 4;

/** Retry chips drawn in the attempts gutter before a `+k` chip stands for the rest. */
export const MAX_RETRY_CHIPS = 4;

/**
 * The word a **Run**'s token says, and the word a **step row**'s token says.
 *
 * They differ at exactly one token, and the difference is the spine's, not an oversight:
 * EXPERIENCE-v1 *State vocabulary* gives `ERR` two readings — a Run is `failed` (terminal),
 * a row is `error` (inside a `BLK` run until retried or skipped). The footer names the Run's
 * state; a card names its own row's. Both live here so neither can drift again, and
 * `run-tree.test.ts` pins the pair and the single difference between them.
 */
const SHARED_STATUS_WORD = {
  QUE: 'queued',
  RUN: 'running',
  BLK: 'blocked',
  CHK: 'checkpoint',
  DON: 'done',
  CAN: 'cancelled',
  SKP: 'skipped',
} as const;

export const RUN_STATUS_WORD: Record<string, string> = { ...SHARED_STATUS_WORD, ERR: 'failed' };
export const STEP_STATUS_WORD: Record<string, string> = { ...SHARED_STATUS_WORD, ERR: 'error' };

/** What a card, a strip entry and a screen reader all call a row's state. One helper, so the
 * three cannot answer an unknown token three different ways. An unrecognised token is
 * printed verbatim rather than lower-cased into something that reads like a word: it is an
 * identifier this build does not know, and saying so is the honest answer (AD-8 — the UI
 * renders the tokens the writers stored). */
export function statusWord(token: string | null): string {
  if (token === null) return 'no status';
  return STEP_STATUS_WORD[token] ?? token;
}

/** The column head above a rank, chosen by what the rank actually holds. */
export const RANK_HEADS = {
  run: 'RUN',
  epics: 'EPICS',
  stories: 'STORIES',
  storiesAndAgents: 'STORIES + EPIC AGENTS',
  agents: 'AGENTS',
} as const;

export type Rank = number;
export type NodeKind = 'root' | 'epic' | 'story' | 'agent';

/**
 * What the card's border says. `inflight` is the 2026-09-24 ratification: the blue border
 * belongs to the current step alone, so a `running` **ancestor** carries `line-strong` and
 * keeps the blue `RUN` word token. `error | blocked | checkpoint` keep their colour at every
 * level, because the path to a stop must be findable by colour from the root down. `none` is
 * what an unrecognised value gets: the hairline the card already has, and no claim.
 */
export type BorderState =
  | 'done'
  | 'running'
  | 'inflight'
  | 'error'
  | 'blocked'
  | 'checkpoint'
  | 'queued'
  | 'skipped'
  | 'cancelled'
  | 'none';

export interface GuardrailEntry {
  /** The row's own step id — the last path segment; the `-<step-id>` of its test id. */
  stepId: string;
  /** The row's full bracket path, for the STEPS tab reader who wants to find it. */
  path: string;
  /** The step word shown in the strip. */
  label: string;
  /** The 4px dot's state — the diagram dialect, undemoted (a running row's dot is blue). */
  dot: BorderState;
  token: string | null;
  /** The word the dot says, so colour is never the strip's only carrier. */
  word: string;
  /** This row is a stop: it survives truncation ahead of every settled row. */
  stop: boolean;
}

export interface Guardrail {
  /** The node id of the epic, story or root the strip sits on. */
  ownerId: string;
  /** That node's dot-index path — the `<path>` of `wf-diagram-guardrail-<path>`. */
  ownerPath: string;
  entries: GuardrailEntry[];
  /** How many further entries the strip did not draw; `0` when none were dropped. */
  overflow: number;
  /** Every entry is still queued, so the whole strip is drawn quieter still. */
  muted: boolean;
}

export interface RetryChip {
  /** 1-based: `try 1`, `try 2`. */
  n: number;
  label: string;
  /** Only the latest failed attempt can state one — the wire carries no earlier code. */
  exitCode: number | null;
}

export interface HierarchyNode {
  /** The graph id: `root`, a group id, or an agent row's `step_run.path`. */
  id: string;
  /** `id` in dot-index form — every path-bearing test id and the CTA href use this. */
  path: string;
  /** The column this card is drawn in, after empty ranks are dropped. */
  rank: Rank;
  kind: NodeKind;
  parentId: string | null;
  /** What holds this card — an agent under a story is narrower than one under an epic. */
  parentKind: NodeKind | null;
  title: string;
  eyebrow: string;
  token: string | null;
  border: BorderState;
  current: boolean;
  /** The card's `{typography.meta}` line: `k/n steps`, `claude · sonnet · 3 attempts`, … */
  meta: string;
  /** An agent card's duration, or `null` where the card carries none. */
  duration: string | null;
  /** Epic and story nodes carry a caret; a childless one has nothing to open. */
  expandable: boolean;
  expanded: boolean;
  guardrail: Guardrail | null;
  retries: RetryChip[];
  /** Failed attempts the gutter did not draw; `0` when every one of them fits. */
  retryOverflow: number;
  /** `/workflows/{runId}/steps/{path}` needs a joined row; `false` omits the CTA. */
  joined: boolean;
}

export interface Hierarchy {
  /** One bucket per column actually drawn, each in spec order. Never holds an empty rank. */
  ranks: HierarchyNode[][];
  /** The column head above each rank of `ranks`, same length, same order. */
  heads: string[];
  /** Every strip drawn, in the order its owner is drawn. */
  guardrails: Guardrail[];
  /** Every agent node that retried, with its chips oldest first. */
  retries: { nodeId: string; chips: RetryChip[]; overflow: number }[];
  /** The same nodes, flat and visible-only, in rank-then-spec order. */
  nodes: HierarchyNode[];
  /** Parent-rank → child-rank only. Never between two siblings. */
  edges: { id: string; from: string; to: string }[];
}

/**
 * The two frame shapes, matched the same way: a group id *ends with* the loop segment.
 *
 * `_group_prefixes` writes whatever prefix the plan nests the row under, so an `epics[i]` is
 * not always top-level — a multi-repo initiative plans `repos[0].epics[1]`. Anchoring the
 * epic pattern at the start (and not the story one) made that id match neither, which
 * re-parented its whole subtree to the root.
 */
const EPIC_GROUP = /(^|\.)epics\[\d+\]$/;
const STORY_GROUP = /(^|\.)stories\[\d+\]$/;

const TOKEN_BY_STATUS: Record<string, string> = {
  planned: 'QUE',
  queued: 'QUE',
  running: 'RUN',
  done: 'DON',
  blocked: 'BLK',
  checkpoint: 'CHK',
  error: 'ERR',
  skipped: 'SKP',
  needs_you: 'BLK',
  failed: 'ERR',
  cancelled: 'CAN',
};

const BORDER_BY_TOKEN: Record<string, BorderState> = {
  DON: 'done',
  RUN: 'running',
  BLK: 'blocked',
  CHK: 'checkpoint',
  ERR: 'error',
  QUE: 'queued',
  SKP: 'skipped',
  CAN: 'cancelled',
};

/**
 * The statuses whose newest attempt is itself a failure.
 *
 * `error` is the agent exiting non-zero; `blocked` is it handing back unable to finish. Every
 * other status means the newest attempt has not failed — `done` and `skipped` because it
 * succeeded, `running` because it is still in flight, and `checkpoint` because a checkpoint
 * park is the *designed* stop and a red `failed` chip there would state a failure the run
 * never had (operator correction, 2026-09-24).
 */
const LATEST_FAILED = new Set(['error', 'blocked']);

/** The strip entries that must survive truncation — the path to a stop stays findable. */
const STOP_BORDERS = new Set<BorderState>(['error', 'blocked', 'checkpoint']);

/**
 * The glyph a guardrail dot draws, one shape per state.
 *
 * A 4px square differing only in hue is colour alone to anyone who cannot separate the hues,
 * and the strip has no room for the word beside it (`sync done · verify queued ·
 * commit-guard queued` does not fit a 228px story card). Monospace keeps every glyph one
 * cell wide, so the strip still aligns. The word is still there for a screen reader.
 */
export const DOT_GLYPH: Record<BorderState, string> = {
  done: '\u25a0',
  running: '\u25b6',
  inflight: '\u25b6',
  error: '\u2715',
  blocked: '\u25b2',
  checkpoint: '\u25c6',
  queued: '\u25a1',
  skipped: '\u2013',
  cancelled: '\u2013',
  none: '?',
};

/**
 * The parent of a path: everything before the last `.`, or the root.
 *
 * `epics[0].stories[3].build` → `epics[0].stories[3]`; `epics[0]` → `root`. A step id may
 * carry hyphens (`commit-guard`) but never a dot, and a loop index lives inside its own
 * segment's brackets, so splitting on `.` is exact.
 */
export function parentOf(id: string): string {
  const at = id.lastIndexOf('.');
  return at === -1 ? ROOT_ID : id.slice(0, at);
}

/** The nearest ancestor of `id` that is a drawn container, or the root. */
function containerOf(id: string, containers: Set<string>): string {
  let cursor = parentOf(id);
  while (cursor !== ROOT_ID) {
    if (containers.has(cursor)) return cursor;
    cursor = parentOf(cursor);
  }
  return ROOT_ID;
}

/**
 * The token a node shows: the row's own, else the one its status word maps to, else nothing.
 *
 * A value neither map knows answers `null` rather than a confident `QUE`. AD-8 puts status in
 * the hands of `apply_step_result`/`signal_run` and the UI renders what they stored; inventing
 * "queued" for a word this build has not met would be the diagram deriving a status, and it
 * would read as a fact rather than as the contract drift it is.
 */
function tokenOf(status: string | null | undefined, token?: string | null): string | null {
  if (token) return token;
  if (!status) return null;
  if (/^[A-Z]{3}$/.test(status)) return status;
  return TOKEN_BY_STATUS[status] ?? null;
}

/** The border rule, including the one-blue-node ratification (see `BorderState`). */
export function borderOf(token: string | null, current: boolean): BorderState {
  if (token === null) return 'none';
  const base = BORDER_BY_TOKEN[token];
  if (base === undefined) return 'none';
  if (base === 'running' && !current) return 'inflight';
  return base;
}

/** `18m 47s`, `1h 04m`, or `—` when the wire carries no duration for the row. */
export function durationText(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—';
  const total = Math.max(0, Math.round(seconds));
  if (total >= 3600) {
    return `${Math.floor(total / 3600)}h ${String(Math.floor((total % 3600) / 60)).padStart(2, '0')}m`;
  }
  return `${String(Math.floor(total / 60)).padStart(2, '0')}m ${String(total % 60).padStart(2, '0')}s`;
}

/**
 * How many attempts of this row failed.
 *
 * `StepRowOut.attempts` counts attempt rows including the one in flight
 * (`use_cases/run_views.py:313`), so the newest attempt only counts as a failure when the row
 * itself says it failed — `error` or `blocked`. `done`, `skipped`, `running` and `checkpoint`
 * all mean the newest attempt did not fail, so they answer `attempts - 1`.
 */
export function failedAttempts(row: Pick<StepRowOut, 'attempts' | 'status'>): number {
  return Math.max(0, row.attempts - (LATEST_FAILED.has(row.status) ? 0 : 1));
}

/**
 * The chips of one agent row, capped so a runaway retry count cannot flood the canvas:
 * the **newest** `MAX_RETRY_CHIPS` of them, oldest of those first, and a count of the rest.
 *
 * Newest, not first: the only exit code on the wire belongs to the latest failed attempt, so
 * keeping the oldest four threw away the one chip that could say `exit 1` — silently, and
 * exactly on the runs that failed most. The overflow count stands for the attempts before
 * them, and `flow-layout.ts` draws its chip above the stack, where they happened.
 */
export function retriesOf(row: StepRowOut | undefined): {
  chips: RetryChip[];
  overflow: number;
} {
  if (row === undefined) return { chips: [], overflow: 0 };
  const failed = failedAttempts(row);
  // only the newest attempt's exit code is on the wire, and only when it is itself the
  // failure — a `done` or `checkpoint` row's `latest` did not fail, and printing its code on
  // a failed chip would state something the run never said.
  const latestCode = LATEST_FAILED.has(row.status) ? (row.latest?.exit_code ?? null) : null;
  const overflow = Math.max(0, failed - MAX_RETRY_CHIPS);
  const chips = Array.from({ length: failed - overflow }, (_, index) => {
    const n = overflow + index + 1;
    return { n, label: `try ${n}`, exitCode: n === failed ? latestCode : null };
  });
  return { chips, overflow };
}

/** `epic 1` / `story 4-1`: the label segment at this frame's own depth. */
function frameTitle(group: RunGroupOut, firstMemberLabel: string | undefined): string {
  const depth = group.id.split('.').length;
  const segments = (firstMemberLabel ?? '').split(' · ');
  return segments[depth - 1] ?? group.id;
}

/** An agent card's title: the row's own name, without the frames that hold it. */
function leafTitle(node: RunNodeOut): string {
  const segments = node.label.split(' · ');
  return segments[segments.length - 1] ?? node.label;
}

/** `claude · sonnet`, plus `n attempts` once there is more than one. */
function agentMeta(row: StepRowOut | undefined): string {
  const parts: string[] = [];
  if (row?.latest?.harness) parts.push(row.latest.harness);
  if (row?.latest?.model) parts.push(row.latest.model);
  if (row !== undefined && row.attempts > 1) parts.push(`${row.attempts} attempts`);
  return parts.join(' · ');
}

/**
 * The root card's meta line. `n epics · m stories` is the artboard's, and it is what a
 * frame-bearing Run has to say; a Run with no frames at all would otherwise read
 * `0 epics · 0 stories`, which states two absences and no fact — it says its size instead.
 */
function rootMeta(epics: number, stories: number, rows: number): string {
  const storyWord = `${stories} stor${stories === 1 ? 'y' : 'ies'}`;
  if (epics > 0) return `${epics} epic${epics === 1 ? '' : 's'} · ${storyWord}`;
  if (stories > 0) return storyWord;
  return `${rows} step${rows === 1 ? '' : 's'}`;
}

/** The head above a column, from the kinds of card standing in it. */
function headFor(column: HierarchyNode[]): string {
  const kinds = new Set(column.map((node) => node.kind));
  if (kinds.has('root')) return RANK_HEADS.run;
  if (kinds.has('story')) {
    return kinds.has('agent') ? RANK_HEADS.storiesAndAgents : RANK_HEADS.stories;
  }
  if (kinds.has('epic')) return RANK_HEADS.epics;
  return RANK_HEADS.agents;
}

/**
 * The ids to expand on the first fetch: every ancestor of the current step, so the path to
 * what is running (or stopped) is open and every other epic starts collapsed.
 */
export function defaultExpanded(graph: RunGraphOut): Set<string> {
  const current = graph.nodes.find((node) => node.current);
  const open = new Set<string>();
  if (current === undefined) return open;
  let cursor = parentOf(current.id);
  while (cursor !== ROOT_ID) {
    open.add(cursor);
    cursor = parentOf(cursor);
  }
  return open;
}

/** The node the Run is on, or `null` — `current` is set on rows, never on a group. */
export function findCurrentStep(graph: RunGraphOut): RunNodeOut | null {
  return graph.nodes.find((node) => node.current) ?? null;
}

/**
 * The whole v3 model: which cards are drawn, in which column, with which guardrail strip and
 * which retry chips. `expanded` holds the ids of the epic and story nodes the operator (or
 * `defaultExpanded`) has opened; a node is drawn only when every ancestor of it is open.
 */
export function buildHierarchy(
  graph: RunGraphOut,
  steps: StepRowOut[],
  expanded: Set<string>,
): Hierarchy {
  const rowByPath = new Map(steps.map((row) => [row.path, row]));
  const epicGroups = graph.groups.filter((group) => EPIC_GROUP.test(group.id));
  const storyGroups = graph.groups.filter((group) => STORY_GROUP.test(group.id));
  const containers = new Set([...epicGroups, ...storyGroups].map((group) => group.id));

  // Spec order is the plan's own order: `graph.nodes` arrives in `seq`, and a frame starts
  // where its first row does (`graph.py::_group_prefixes`).
  const seqOf = new Map<string, number>();
  graph.nodes.forEach((node, index) => seqOf.set(node.id, index));
  for (const group of [...epicGroups, ...storyGroups]) {
    const first = group.members
      .map((member) => seqOf.get(member))
      .filter((at): at is number => at !== undefined);
    seqOf.set(group.id, first.length > 0 ? Math.min(...first) : Number.MAX_SAFE_INTEGER);
  }
  const order = (id: string) => seqOf.get(id) ?? Number.MAX_SAFE_INTEGER;

  const built = new Map<string, HierarchyNode>();
  /** The classification depth, before empty ranks collapse: 0 root · 1 epic · 2 · 3. */
  const depth = new Map<string, number>();

  // The root is built whenever the graph has any row at all, whether or not the graph names
  // one. It is where every row outside a frame hangs, and the guardrail loop below drops an
  // entry whose owner does not exist — so a graph without a `root` node used to lose every
  // frame-less row in silence, which is the one thing the build-implies-draw rule forbids.
  const rootNode = graph.nodes.find((node) => node.id === ROOT_ID);
  if (graph.nodes.length > 0) {
    const token = rootNode === undefined ? null : tokenOf(rootNode.status, rootNode.token);
    depth.set(ROOT_ID, 0);
    built.set(ROOT_ID, {
      id: ROOT_ID,
      path: ROOT_ID,
      rank: 0,
      kind: 'root',
      parentId: null,
      parentKind: null,
      // a graph that named no root said nothing about the Run either: the card states what
      // it is and leaves the state to the token it does not have
      title: rootNode?.label ?? 'run',
      eyebrow: rootNode?.kind ?? 'run',
      token,
      border: borderOf(token, false),
      current: false,
      meta: rootMeta(
        epicGroups.length,
        storyGroups.length,
        graph.nodes.length - (rootNode === undefined ? 0 : 1),
      ),
      duration: null,
      expandable: false,
      expanded: true,
      guardrail: null,
      retries: [],
      retryOverflow: 0,
      joined: false,
    });
  }

  const labelOfFirstMember = (group: RunGroupOut): string | undefined => {
    const first = [...group.members].sort((a, b) => order(a) - order(b))[0];
    return first === undefined
      ? undefined
      : (graph.nodes.find((node) => node.id === first)?.label ?? rowByPath.get(first)?.label);
  };

  for (const group of [...epicGroups, ...storyGroups]) {
    const isEpic = EPIC_GROUP.test(group.id);
    const parentId = containerOf(group.id, containers);
    const token = tokenOf(group.status);
    depth.set(group.id, isEpic ? 1 : 2);
    built.set(group.id, {
      id: group.id,
      path: encode(group.id),
      rank: isEpic ? 1 : 2,
      kind: isEpic ? 'epic' : 'story',
      parentId,
      parentKind: null,
      title: frameTitle(group, labelOfFirstMember(group)),
      eyebrow: isEpic ? 'epic' : 'story',
      token,
      border: borderOf(token, false),
      current: false,
      meta: isEpic ? `${group.k ?? 0}/${group.n ?? 0} steps` : '',
      duration: null,
      expandable: false,
      expanded: expanded.has(group.id),
      guardrail: null,
      retries: [],
      retryOverflow: 0,
      joined: false,
    });
  }

  for (const node of graph.nodes) {
    if (node.id === ROOT_ID || !node.agent) continue;
    const parentId = containerOf(node.id, containers);
    const parent = built.get(parentId);
    const row = rowByPath.get(node.id);
    const token = tokenOf(node.status, node.token);
    const retries = retriesOf(row);
    depth.set(node.id, parent?.kind === 'story' ? 3 : 2);
    built.set(node.id, {
      id: node.id,
      path: encode(node.id),
      rank: parent?.kind === 'story' ? 3 : 2,
      kind: 'agent',
      parentId,
      parentKind: parent?.kind ?? null,
      title: leafTitle(node),
      eyebrow: node.current ? 'now' : 'agent',
      token,
      border: borderOf(token, node.current),
      current: node.current,
      meta: agentMeta(row),
      duration: durationText(row?.latest?.seconds),
      expandable: false,
      expanded: true,
      guardrail: null,
      retries: retries.chips,
      retryOverflow: retries.overflow,
      joined: row !== undefined,
    });
  }

  // Every row that is not drawn becomes a guardrail entry on the container that owns it —
  // the root included, which is where `plan` and a hub Run's `checkout`/`submodules` live.
  for (const node of graph.nodes) {
    if (node.id === ROOT_ID || node.agent) continue;
    // the root is built for every non-empty graph, so `containerOf`'s fallback always
    // resolves and no entry is ever collected for an owner that will not draw it
    const owner = built.get(containerOf(node.id, containers))!;
    const token = tokenOf(node.status, node.token);
    const dot = token === null ? 'none' : (BORDER_BY_TOKEN[token] ?? 'none');
    const entry: GuardrailEntry = {
      stepId: node.id.slice(node.id.lastIndexOf('.') + 1),
      path: node.id,
      label: leafTitle(node),
      dot,
      token,
      word: statusWord(token),
      stop: STOP_BORDERS.has(dot),
    };
    if (owner.guardrail === null) {
      owner.guardrail = {
        ownerId: owner.id,
        ownerPath: owner.path,
        entries: [entry],
        overflow: 0,
        muted: true,
      };
    } else {
      owner.guardrail.entries.push(entry);
    }
  }

  for (const node of built.values()) {
    if (node.guardrail !== null) node.guardrail = truncate(node.guardrail);
  }

  for (const node of built.values()) {
    if (node.parentId === null) continue;
    const parent = built.get(node.parentId);
    if (parent !== undefined && (parent.kind === 'epic' || parent.kind === 'story')) {
      parent.expandable = true;
    }
  }

  // A card is drawn only when every ancestor of it is open.
  const visible = (node: HierarchyNode): boolean => {
    let cursor = node.parentId;
    while (cursor !== null) {
      const parent = built.get(cursor);
      if (parent === undefined) return true;
      if (parent.expandable && !parent.expanded) return false;
      cursor = parent.parentId;
    }
    return true;
  };

  const drawn = [...built.values()]
    .filter(visible)
    .sort((a, b) => depth.get(a.id)! - depth.get(b.id)! || order(a.id) - order(b.id));

  // Ranks collapse to what exists: an empty column is not drawn and its head is not printed.
  const columns = [...new Set(drawn.map((node) => depth.get(node.id)!))].sort((a, b) => a - b);
  const rankOf = new Map(columns.map((original, index) => [original, index]));
  for (const node of drawn) node.rank = rankOf.get(depth.get(node.id)!)!;

  const ranks: HierarchyNode[][] = columns.map(() => []);
  for (const node of drawn) ranks[node.rank]!.push(node);

  const present = new Set(drawn.map((node) => node.id));
  const edges = drawn
    .filter((node) => node.parentId !== null && present.has(node.parentId))
    .map((node) => ({ id: `${node.parentId}->${node.id}`, from: node.parentId!, to: node.id }));

  return {
    ranks,
    heads: ranks.map(headFor),
    guardrails: drawn
      .map((node) => node.guardrail)
      .filter((strip): strip is Guardrail => strip !== null),
    retries: drawn
      .filter((node) => node.retries.length > 0)
      .map((node) => ({ nodeId: node.id, chips: node.retries, overflow: node.retryOverflow })),
    nodes: drawn,
    edges,
  };
}

/**
 * A strip cut to `MAX_GUARDRAIL_ENTRIES`, with every stop kept.
 *
 * Cutting in plan order alone would drop a `blocked` row sitting sixth out of eight, and with
 * it the invariant that the path to a stop is findable by colour from the root down. So the
 * stops are chosen first and the rest fill the remaining places — and then the chosen set is
 * put back into plan order, because a strip that re-sorts itself around a stop is a strip
 * whose reading order changes under the operator (operator amendment, 2026-09-24).
 */
function truncate(strip: Guardrail): Guardrail {
  const all = strip.entries;
  const muted = all.every((entry) => entry.token === 'QUE' || entry.token === null);
  if (all.length <= MAX_GUARDRAIL_ENTRIES) {
    return { ...strip, muted, overflow: 0 };
  }
  const chosen = new Set<GuardrailEntry>();
  for (const entry of all) {
    if (entry.stop && chosen.size < MAX_GUARDRAIL_ENTRIES) chosen.add(entry);
  }
  for (const entry of all) {
    if (chosen.size >= MAX_GUARDRAIL_ENTRIES) break;
    chosen.add(entry);
  }
  return {
    ...strip,
    muted,
    entries: all.filter((entry) => chosen.has(entry)),
    overflow: all.length - chosen.size,
  };
}

/**
 * The footer readout under the tree (EXPERIENCE-v1 §2.2):
 * `step 15 of 22 · epic 1 · story 4-1 · build · blocked 2d 04h · 5/8 stories`.
 *
 * Single-line context, so the step is named by its **label**, never its path (naming rule).
 */
export function footerText(
  current: { seq: number; label: string } | null,
  totals: { steps: number; storiesDone: number; stories: number },
  state: { word: string; age: string },
): string {
  const tail = `${totals.storiesDone}/${totals.stories} stories`;
  if (current === null) return tail;
  return (
    `step ${current.seq} of ${totals.steps} · ${current.label} · ` +
    `${state.word} ${state.age} · ${tail}`
  );
}
