/**
 * The pure helpers of the forced start and the cancel of an initiative (story 11.4). Every
 * status, token and line is the API's; nothing here computes one.
 */
import { turnTime } from './conversation';
import { shortId } from './files';
import { isInteractive, type DetailStep, type DetailWorkflow, type InitiativeDetail } from './page';

function currentStep(d: InitiativeDetail, w: DetailWorkflow): DetailStep | null {
  if (d.status === 'cancelled' || w.position !== d.current_position || !isInteractive(w)) {
    return null;
  }
  return w.steps.find((s) => s.id === d.current_step) ?? null;
}

export function forceTarget(d: InitiativeDetail, w: DetailWorkflow): string | null {
  const c = currentStep(d, w);
  if (!c || c.kind !== 'conversation' || c.park_kind !== 'conversation' || c.park_seq === null) {
    return null;
  }
  const next = w.steps[w.steps.indexOf(c) + 1];
  // The backend refuses a next step outside a named round (a reopen), so it is not offered.
  const round = d.owners ?? [];
  return next && next.kind === 'conversation' && (round.length === 0 || round.includes(next.id))
    ? next.id
    : null;
}

export function forceParkSeq(d: InitiativeDetail, w: DetailWorkflow): number | null {
  return currentStep(d, w)?.park_seq ?? null;
}

export function forceHead(next: string): string {
  return `START ${next.toUpperCase()} NOW`;
}

export function forceQuestion(current: string): string {
  return `Are you sure? If step «${current.toUpperCase()}» is not done this workflow might fail.`;
}

export function forceMechanism(
  current: string,
  next: string,
  slug: string,
  workflow: string,
  nextWorkflow: string | null,
): string {
  const cap = next.charAt(0).toUpperCase() + next.slice(1);
  const base = `The ${current.toUpperCase()} step closes as skipped, forced; its conversation and its draft files are kept. ${cap} starts with what is on spec/${slug} now.`;
  return nextWorkflow
    ? `${base} The gate is never forced, so ${nextWorkflow} cannot start before ${workflow} passes it.`
    : base;
}

export function keepLabel(current: string): string {
  return `Keep ${current} open`;
}

export function startLabel(next: string): string {
  return `Start ${next}`;
}

export function showsCancel(status: InitiativeDetail['status']): boolean {
  return status !== 'done' && status !== 'cancelled';
}

export function cancelLines(d: InitiativeDetail): string[] {
  const w = d.workflows.find((x) => x.position === d.current_position);
  const open =
    w !== undefined &&
    isInteractive(w) &&
    (d.sessions ?? []).some(
      (s) =>
        s.kind === 'session' &&
        s.workflow === d.workflow &&
        s.step === d.current_step &&
        s.state === 'open',
    );
  const lines = [`spec/${d.slug} is deleted`];
  if (open) lines.push(`The open ${d.current_step} session is cancelled`);
  else if (w?.run_id) lines.push(`Run ${shortId(w.run_id)} is cancelled`);
  lines.push('Files already merged into main stay; nothing is removed from main');
  lines.push(`The slug ${d.slug} is free again`);
  return lines;
}

export function cancelledStateLine(d: InitiativeDetail): string {
  return `cancelled at ${d.step}${d.cancelled_at ? ` · ${turnTime(d.cancelled_at)}` : ''}`;
}

export function forcedLine(
  previous: DetailStep | null,
  step: DetailStep,
  slug: string,
): string | null {
  if (previous?.token !== 'SKP') return null;
  const at = /· (\d{2}:\d{2})$/.exec(previous.line)?.[1];
  return `${previous.id} skipped, forced${at ? ` at ${at}` : ''} · its files on spec/${slug} are what ${step.id} reads`;
}
