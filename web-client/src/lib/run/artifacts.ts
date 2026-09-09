/**
 * The ARTIFACTS column's own pure facts (6.3, FR-19, FR-23, UX-DR9): the request paths
 * `GET`/`PUT /runs/{id}/files` (6.2 read, 6.3 tree + write) are called at, which files are
 * list files a plan already read (read-only, never an Edit control), whether one Markdown-
 * renders or prints as plain text, the tree's own indent depth, its `mtime`'s own text, and
 * the two sentences the hint line and the read-only line show verbatim.
 *
 * Kept out of `ArtifactsPanel.tsx` and its siblings the same way `checkpoint.ts` is kept out
 * of `StopBody.tsx`: this module unit-tests without a DOM (`web-client/AGENTS.md`).
 */
import type { components } from '../../api/schema';
import type { RunDetailOut } from './detail';

export type RunFileOut = components['schemas']['RunFileOut'];
export type RunFileEntryOut = components['schemas']['RunFileEntryOut'];
export type RunFilesTreeOut = components['schemas']['RunFilesTreeOut'];
type RunSummary = RunDetailOut['run'];

/** `GET /runs/{id}/files` with no `path` — the tree. */
export function treeRequestPath(runId: string): string {
  return `/api/runs/${runId}/files`;
}

/** `GET /runs/{id}/files?path=...` — one file's content. */
export function fileRequestPath(runId: string, path: string): string {
  return `/api/runs/${runId}/files?path=${encodeURIComponent(path)}`;
}

/** The two list files a plan reads (`Run.plan_refs`'s own two keys): read-only always,
 * whether or not this particular Run's plan happened to name them (the server-side gate
 * is the real one — `write_run_file`'s own `409 planned at {sha}` — this is only what
 * hides the Edit control before a save is even attempted). */
export function isListFile(folder: string, path: string): boolean {
  return path === `${folder}/stories.yaml` || path === `${folder}/epics.yaml`;
}

/** Whether a path renders through the Markdown block renderer, or prints as plain text
 * (`.yaml` included — "YAML as text", the brief's own words). */
export function isMarkdown(path: string): boolean {
  return path.endsWith('.md');
}

/** The editor's own hint line, verbatim (the brief's own words). Shown beside the textarea
 * whether or not a save has happened yet, `AnswerBox`'s own precedent. */
export function editHint(branch: string): string {
  return `saved as commit "spec: operator edit (orchestrator)" on ${branch}`;
}

/** The read-only line a list file opens with, verbatim (the brief's own words) — `planRef`
 * is `run.plan_ref` (singular, already on the wire): see this module's own doc for why the
 * per-file `run.plan_refs` sha is not published to the client. */
export function readOnlyLine(planRef: string | null): string {
  return `planned at ${planRef ?? '—'} — start a new run to change the list`;
}

/** The 14px indent multiplier `ArtifactsTree` renders each row at: how many path segments
 * `path` holds under `root`, `0` for the root's own direct children. */
export function treeDepth(path: string, root: string): number {
  if (!root || path === root) return 0;
  const prefix = `${root}/`;
  const relative = path.startsWith(prefix) ? path.slice(prefix.length) : path;
  return relative.split('/').length - 1;
}

/** `mtime`'s own ISO text (Consistency Conventions — Dates), right-aligned beside the
 * filename (`DESIGN.md`'s own artifact-tree shape) — `''` for a directory row, which has
 * no `mtime` of its own (`RunFileEntryOut.of`'s own `0.0`). */
export function mtimeText(entry: RunFileEntryOut): string {
  if (entry.kind === 'dir') return '';
  return new Date(entry.mtime * 1000).toISOString();
}

/** The path's own last segment — what a tree row's filename column shows. */
export function fileName(path: string): string {
  const parts = path.split('/');
  return parts[parts.length - 1] ?? path;
}

/** Whether the Edit control shows for this path: a parked Run, no terminal session, and
 * not one of the two list files (`isListFile`'s own gate). */
export function canEditFile(run: RunSummary, path: string, folder: string): boolean {
  return run.status === 'needs_you' && !run.terminal_session && !isListFile(folder, path);
}

/** The GET response is `RunFileOut | RunFilesTreeOut` (no `path` given answers the tree) —
 * this is the one place that tells them apart, by the field only the tree carries. */
export function isTree(data: RunFileOut | RunFilesTreeOut): data is RunFilesTreeOut {
  return 'entries' in data;
}
