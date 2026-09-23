/**
 * Pure derivations `EpicList.tsx`/`RepoTable.tsx` render an `InitiativePreflightOut` from
 * (S7) — kept out of the components so they unit-test without a DOM (`web-client/AGENTS.md`).
 */
import type { components } from '../../api/schema';

type EpicPreflightOut = components['schemas']['EpicPreflightOut'];

/** `InitiativeRepoOut.remote_holds_branch`, as the word the repo table prints: the branch
 * already existed on the remote ("adopted") or this dispatch would create it ("created"). */
export function branchStateText(remoteHoldsBranch: boolean): string {
  return remoteHoldsBranch ? 'adopted' : 'created';
}

/** `depends_on`/a checkpoint kind/a working branch, joined or dashed — never a blank cell. */
export function listText(items: string[]): string {
  return items.length > 0 ? items.join(', ') : '—';
}

export function orDash(value: string | null): string {
  return value ?? '—';
}

/** `order[]`, as the readout beside the epic list — `'—'` for the one case `order` is ever
 * empty: a `fail` line already said the graph has a cycle (`InitiativePreflightOut.order`'s
 * own doc), and an empty arrow chain would otherwise read as "there are no epics at all". */
export function orderText(order: string[]): string {
  return order.length > 0 ? order.join(' → ') : '—';
}

export interface EpicGroup {
  repositoryId: string | null;
  repository: string | null;
  epics: EpicPreflightOut[];
}

/**
 * Epics grouped by the repository they land in, groups and epics both in `order[]`'s own
 * topological sequence — `epics[]` itself carries no such promise (`EpicPreflightOut`'s own
 * doc only says "the graph it would build", never an order). An epic `order` does not name —
 * only possible when a `fail` line already refused the whole dispatch on a cycle, per
 * `InitiativePreflightOut.order`'s own doc — still renders, appended after every epic the
 * order did name, so a refused pre-flight never drops a row silently. A `null`
 * `repository_id` (that same cycle refusal) groups under its own trailing group instead of
 * being folded into a real repository's rows.
 */
export function epicsByRepository(epics: EpicPreflightOut[], order: string[]): EpicGroup[] {
  const byId = new Map(epics.map((epic) => [epic.epic_id, epic] as const));
  const named = new Set(order);
  const ordered = order
    .map((id) => byId.get(id))
    .filter((epic): epic is EpicPreflightOut => epic !== undefined);
  const remaining = epics.filter((epic) => !named.has(epic.epic_id));
  const sequence = [...ordered, ...remaining];

  const groups: EpicGroup[] = [];
  const indexByKey = new Map<string, number>();
  for (const epic of sequence) {
    const key = epic.repository_id ?? '';
    let index = indexByKey.get(key);
    if (index === undefined) {
      index = groups.length;
      indexByKey.set(key, index);
      groups.push({ repositoryId: epic.repository_id, repository: epic.repository, epics: [] });
    }
    groups[index]!.epics.push(epic);
  }
  return groups;
}
