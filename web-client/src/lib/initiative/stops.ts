/**
 * The pure helpers of the Initiative page's stops: which banner shows, its lines, the restart
 * the facts call for, and the gate's defects. Every token, status, reason and failure reason is
 * the API's; only fixed copy, counts and positions are composed here.
 */
import { listedTurns, turnTime, type Turn } from './conversation';
import {
  isInteractive,
  statusTokenWord,
  type DetailStep,
  type DetailWorkflow,
  type InitiativeDetail,
} from './page';

export const NO_BUDGET = 'no project budget';
export const WAITING_MERGE = 'waiting for the pull request merge';
export const NOT_CLOSED = 'step not closed';

export type Restart =
  { kind: 'retry'; runId: string } | { kind: 'reopen'; step: string; reason: string };

export interface Banner {
  kind: 'merge' | 'stalled' | 'failed' | 'advance' | 'budget';
  tone: 'amber' | 'red';
  head: string;
  body: string | null;
  restart: Restart | null;
  workflow?: string;
}

export function isMergeConflict(step: DetailStep): boolean {
  return step.park_kind === 'merge_conflict';
}

export function lastListed(step: DetailStep): Turn | null {
  return listedTurns(step.turns ?? []).at(-1) ?? null;
}

export function doneCount(step: DetailStep): number {
  const done = listedTurns(step.turns ?? []).filter((t) => t.status === 'done');
  return done.at(-1)?.n ?? 0;
}

export function failedTurnLine(
  step: DetailStep,
): { text: string; runId: string; attemptId: string } | null {
  const last = lastListed(step);
  if (!last || last.status !== 'failed') return null;
  const reason = last.failure_reason ? `${last.failure_reason} · ` : '';
  return {
    text: `turn ${last.n} failed · ${reason}`,
    runId: last.run_id,
    attemptId: last.attempt_id,
  };
}

function headOf(d: InitiativeDetail, step: DetailStep): string {
  return d.reason || lastListed(step)?.failure_reason || statusTokenWord(d.status).word;
}

function hasOpenSession(d: InitiativeDetail, w: DetailWorkflow, step: DetailStep): boolean {
  return (d.sessions ?? []).some(
    (s) =>
      s.kind === 'session' && s.workflow === w.workflow && s.step === step.id && s.state === 'open',
  );
}

// A cancelled spec Run reads `failed · Run cancelled` on the initiative, but its workflow keeps
// the Run's own `cancelled` status.
function specRunEnded(d: InitiativeDetail, w: DetailWorkflow): boolean {
  return (
    d.status === 'failed' && isInteractive(w) && (w.status === 'failed' || w.status === 'cancelled')
  );
}

function stalledBanner(d: InitiativeDetail, w: DetailWorkflow, step: DetailStep): Banner {
  const head = headOf(d, step);
  const k = doneCount(step);
  const runFailed = specRunEnded(d, w);
  let restart: Restart | null = null;
  if (lastListed(step)?.status === 'failed' && step.run_id && hasOpenSession(d, w, step)) {
    restart = { kind: 'retry', runId: step.run_id };
  } else if (runFailed) {
    restart = { kind: 'reopen', step: step.id, reason: head };
  }
  return {
    kind: 'stalled',
    tone: 'red',
    head,
    body: `The conversation is kept, ${k} turns. Restart continues the same conversation from turn ${k + 1}; no message is lost.`,
    restart,
  };
}

function budgetBanner(d: InitiativeDetail, target: DetailWorkflow): Banner {
  return {
    kind: 'budget',
    tone: 'amber',
    head: `${target.workflow} not started: project ${d.project_name} has no default budget`,
    body: `A Run's budget is your decision. The value is saved as the project default and the ${target.workflow} starts on feat/${d.slug} from main.`,
    restart: null,
    workflow: target.workflow,
  };
}

export function stopBanner(d: InitiativeDetail, selectedPosition: number): Banner | null {
  if (d.status === 'cancelled' || d.status === 'done' || d.reason === WAITING_MERGE) return null;
  const cw = d.workflows.find((w) => w.position === d.current_position);
  const cs = cw?.steps.find((s) => s.id === d.current_step);
  const onCurrent = selectedPosition === d.current_position;

  if (cw && cs && isMergeConflict(cs)) {
    if (!onCurrent) return null;
    const files = cs.conflict_files ?? [];
    return {
      kind: 'merge',
      tone: 'amber',
      head: `merge conflict · ${files.join(', ')}`,
      body: `The merge agent could not resolve ${files.length} file(s). Nothing is pushed to main until you answer and the agent retries. spec/${d.slug} is kept.`,
      restart: null,
    };
  }
  if (cw && cs?.kind === 'conversation') {
    if (lastListed(cs)?.status === 'failed' || specRunEnded(d, cw)) {
      return onCurrent ? stalledBanner(d, cw, cs) : null;
    }
  }
  if (d.status === 'failed') {
    if (!onCurrent) return null;
    return { kind: 'failed', tone: 'red', head: d.reason || 'failed', body: null, restart: null };
  }
  if (d.status === 'waiting for her' && d.reason === NO_BUDGET) {
    const target =
      d.workflows.find((w) => w.position >= d.current_position && w.run_id === null) ?? cw;
    return target && selectedPosition === target.position ? budgetBanner(d, target) : null;
  }
  if (d.status === 'waiting for her' && d.reason !== '' && !d.reason.startsWith(NOT_CLOSED)) {
    return { kind: 'advance', tone: 'amber', head: d.reason, body: null, restart: null };
  }
  return null;
}

export function ownersLine(
  d: InitiativeDetail,
  step: DetailStep,
  isCurrent: boolean,
): string | null {
  const owners = d.owners ?? [];
  if (!isCurrent || (d.round ?? 1) < 2 || !owners.includes(step.id)) return null;
  const next = owners[owners.indexOf(step.id) + 1];
  return next
    ? `after this step closes, ${next} reopens`
    : 'after this step closes, the gate re-runs · no other step reopens';
}

export function mergeYourTurnLine(step: DetailStep, isCurrent: boolean): string | null {
  return isCurrent && isMergeConflict(step)
    ? 'your turn · nothing is pushed to main until the agent retries'
    : null;
}

export function defectsEyebrow(turn: Turn, step: DetailStep): string {
  const owner = `OWNER ${(turn.owner ?? step.id).toUpperCase()}`;
  return turn.defects === null ? `DEFECTS · ${owner}` : `${turn.defects} DEFECTS · ${owner}`;
}

export function gateAgent(workflow: DetailWorkflow, step: DetailStep): string | null {
  const index = workflow.steps.findIndex((s) => s.id === step.id);
  const gate = workflow.steps.slice(index + 1).find((s) => s.kind === 'automatic');
  return gate?.agent ?? null;
}

export function gateAttribution(turn: Turn, agent: string | null): string {
  return ['Gate', agent, turnTime(turn.started_at)].filter((p) => !!p).join(' · ');
}

export function stopStateLine(d: InitiativeDetail): string | null {
  if (d.status === 'done' && d.pr_merged_at) {
    return `done · pull request merged ${d.pr_merged_at.slice(0, 10)}`;
  }
  if (d.reason === WAITING_MERGE) {
    return `${statusTokenWord(d.status).word} · ${d.workflow} done · ${d.reason}`;
  }
  return null;
}

export function validBudget(raw: string): boolean {
  return /^\d+(\.\d{1,2})?$/.test(raw.trim()) && Number(raw) > 0;
}
