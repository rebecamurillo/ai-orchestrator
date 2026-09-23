/**
 * Pure derivations `InitiativeDetail.tsx` renders an `InitiativeOut` from (S7, `GET
 * /initiatives/{slug}`) — kept out of the island so it unit-tests without a DOM
 * (`web-client/AGENTS.md`, `src/lib/run/detail.ts`'s own split for the single-Run screen).
 *
 * **Pairing.** An epic's merge Run shares its `epic_id` and its `repository_id`
 * (`dispatch_initiative.py`'s own construction: the merge Run's `repository_id` is
 * `member.repository.id`, the same repository the epic Run itself named) — that pair is
 * what `repoGroups` below groups every repository's rows into. The go-live Run carries no
 * `epic_id` at all and is rendered separately, last (S7's own scope: "the go-live Run
 * last").
 *
 * **Edges.** `after_run_ids` names other member Runs by id; `waitsForText` turns each into
 * the waited-on Run's own `epic_id` (falling back to its `run_id` for the one case a
 * dependency is not itself a member of this same read — defensive, `after_run_ids` is never
 * cleared once written, so a member this read does not carry is not a contradiction).
 */
import type { components } from '../../api/schema';

export type InitiativeMemberOut = components['schemas']['InitiativeMemberOut'];
export type InitiativeRepoViewOut = components['schemas']['InitiativeRepoViewOut'];
export type InitiativeOut = components['schemas']['InitiativeOut'];

export type Token = 'QUE' | 'RUN' | 'BLK' | 'CHK' | 'DON' | 'ERR' | 'CAN' | 'SKP';

const LIFECYCLE_TOKENS: Record<Exclude<InitiativeMemberOut['status'], 'needs_you'>, Token> = {
  queued: 'QUE',
  running: 'RUN',
  done: 'DON',
  failed: 'ERR',
  cancelled: 'CAN',
};

/** The member's own token (Consistency Conventions) — `src/lib/run/detail.ts::runToken`'s
 * own rule, duplicated the way that module's own doc already duplicates `RunCard.tsx`'s
 * `StatusToken.astro` mapping: `InitiativeMemberOut` carries `status`/`park_kind` as two
 * flat fields rather than `RunDetailOut`'s `run`/`alert` split, so the two signatures do not
 * line up closely enough to share one function without a wrapper that would cost more than
 * this repeats. */
export function memberToken(
  status: InitiativeMemberOut['status'],
  parkKind: InitiativeMemberOut['park_kind'],
): Token {
  if (status === 'needs_you') return parkKind === 'checkpoint' ? 'CHK' : 'BLK';
  return LIFECYCLE_TOKENS[status];
}

export function memberHref(runId: string): string {
  return `/workflows/${runId}`;
}

export interface EpicPairing {
  epicId: string;
  epic: InitiativeMemberOut | null;
  merge: InitiativeMemberOut | null;
}

export interface RepoGroup {
  repositoryId: string;
  repository: string;
  url: string;
  defaultBranch: string;
  branch: string | null;
  pairs: EpicPairing[];
}

function epicPairs(members: InitiativeMemberOut[], repositoryId: string): EpicPairing[] {
  const epics = members.filter((m) => m.repository_id === repositoryId && m.role === 'epic');
  const merges = members.filter((m) => m.repository_id === repositoryId && m.role === 'merge');
  const ids: string[] = [];
  for (const member of [...epics, ...merges]) {
    if (member.epic_id !== null && !ids.includes(member.epic_id)) ids.push(member.epic_id);
  }
  return ids.map((epicId) => ({
    epicId,
    epic: epics.find((m) => m.epic_id === epicId) ?? null,
    merge: merges.find((m) => m.epic_id === epicId) ?? null,
  }));
}

/** One group per `view.repos[]` row (already "one row per repository a member Run works
 * in", `initiative_view.py::_repos`'s own doc), each carrying that repository's epic/merge
 * pairs in first-seen order. */
export function repoGroups(view: InitiativeOut): RepoGroup[] {
  return view.repos.map((repo) => ({
    repositoryId: repo.repository_id,
    repository: repo.repository,
    url: repo.url,
    defaultBranch: repo.default_branch,
    branch: repo.branch,
    pairs: epicPairs(view.members, repo.repository_id),
  }));
}

/** The go-live members — rendered once, after every repository group. */
export function golivemembers(view: InitiativeOut): InitiativeMemberOut[] {
  return view.members.filter((member) => member.role === 'golive');
}

/** `waits for: {epic ids}` under a member row with at least one edge — `null` for a member
 * with none, so a caller can render it unconditionally (`PlanTable.tsx`'s own
 * `planError`/`null` precedent). */
export function waitsForText(
  member: InitiativeMemberOut,
  members: InitiativeMemberOut[],
): string | null {
  if (member.after_run_ids.length === 0) return null;
  const labels = member.after_run_ids.map((runId) => {
    const found = members.find((candidate) => candidate.run_id === runId);
    return found?.epic_id ?? runId;
  });
  return `waits for: ${labels.join(', ')}`;
}

/** The three statuses `stores/poll.ts`'s cadence question means by "running" for this
 * screen — `queued` and `needs_you` are still holding a repository lock or waiting on the
 * Operator, `board/format.ts::oldestWaitSeconds`'s own reading of the same three states as
 * "not settled yet". */
const ACTIVE_STATUSES: ReadonlySet<InitiativeMemberOut['status']> = new Set([
  'queued',
  'running',
  'needs_you',
]);

export function hasActiveMember(view: InitiativeOut): boolean {
  return view.members.some((member) => ACTIVE_STATUSES.has(member.status));
}

/** The request path `FailedFetch` shows and the one this island's `api.GET` call always
 * makes — computed rather than read off a `Response.url` (`board/format.ts::
 * boardRequestPath`'s own reason). */
export function detailRequestPath(slug: string): string {
  return `/api/initiatives/${encodeURIComponent(slug)}`;
}

/** `NO INITIATIVE UNDER {slug}` — the 404 readout's own headline, verbatim (S7's own text). */
export function notFoundHeadline(slug: string): string {
  return `NO INITIATIVE UNDER ${slug}`;
}
