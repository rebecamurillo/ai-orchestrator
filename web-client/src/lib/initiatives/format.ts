/**
 * The pure mapping and grouping the Initiatives board renders from an `InitiativeListOut`.
 * Status, column, step line and progress all come from the response; nothing here computes
 * them — a status is mapped to its EXPERIENCE § 3 token, items are grouped by the workflow
 * the API names.
 */
import type { components } from '../../api/schema';
import { ageText } from '../board/format';

export type InitiativeRow = components['schemas']['InitiativeRowOut'];
export type InitiativeStatus = InitiativeRow['status'];
export type InitiativeColumnOut = components['schemas']['ColumnOut'];
export type InitiativeCounts = components['schemas']['ListCountsOut'];
export type WorkflowFoot = components['schemas']['WorkflowFootOut'];
export type InitiativeFilter = 'ongoing' | 'needs_you' | 'all';

const TOKENS: Record<InitiativeStatus, { token: string; word: string }> = {
  running: { token: 'RUN', word: 'running' },
  'waiting for her': { token: 'BLK', word: 'needs you' },
  done: { token: 'DON', word: 'done' },
  failed: { token: 'ERR', word: 'failed' },
  cancelled: { token: 'CAN', word: 'cancelled' },
};

export function statusToken(status: InitiativeStatus): { token: string; word: string } {
  return TOKENS[status];
}

export function ageSecondsSince(iso: string, nowMs: number): number {
  return Math.max(0, Math.floor((nowMs - Date.parse(iso)) / 1000));
}

export function readoutText(counts: InitiativeCounts, nowMs: number): string {
  const parts = [`${counts.ongoing} ongoing`];
  if (counts.need_you > 0) parts.push(`${counts.need_you} need you`);
  if (counts.oldest_wait_at !== null) {
    parts.push(`oldest wait ${ageText(ageSecondsSince(counts.oldest_wait_at, nowMs))}`);
  }
  return parts.join(' · ');
}

export function columnHeadName(workflow: string): string {
  return workflow.toUpperCase();
}

export function columnTypeWord(type: string): string {
  return type === 'interactive' ? 'INTERACTIVE' : 'AUTO';
}

export function columnCountText(n: number, k: number): { ongoing: string; needYou: string | null } {
  return { ongoing: `${n} ongoing`, needYou: k > 0 ? `${k} need you` : null };
}

export function cancelledHiddenText(n: number): string {
  return `${n} cancelled, hidden · show`;
}

export function placeItems(
  columns: InitiativeColumnOut[],
  items: InitiativeRow[],
): { byColumn: Map<string, InitiativeRow[]>; done: InitiativeRow[]; cancelled: InitiativeRow[] } {
  const byColumn = new Map<string, InitiativeRow[]>(columns.map((c) => [c.workflow, []]));
  const done: InitiativeRow[] = [];
  const cancelled: InitiativeRow[] = [];
  for (const item of items) {
    if (item.status === 'done') done.push(item);
    else if (item.status === 'cancelled') cancelled.push(item);
    else byColumn.get(item.workflow)?.push(item);
  }
  return { byColumn, done, cancelled };
}

export function footWord(entry: WorkflowFoot): string {
  return entry.state ? `${entry.workflow} · ${entry.state}` : entry.workflow;
}

export function initiativesRequestPath(filter: InitiativeFilter, projectId: string | null): string {
  const project = projectId ? `&project_id=${encodeURIComponent(projectId)}` : '';
  return `/api/initiatives?filter=${filter}${project}`;
}

export function hasRunning(items: InitiativeRow[]): boolean {
  return items.some((i) => i.status === 'running');
}

export function byLastChange(rows: InitiativeRow[]): InitiativeRow[] {
  return [...rows].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
}

export function workflowCellText(row: InitiativeRow): string {
  return `${row.workflow} · ${row.position} of ${row.workflow_count}`;
}
