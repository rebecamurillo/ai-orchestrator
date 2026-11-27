/**
 * The pure helpers the Initiative page renders from an `InitiativeDetailOut`. Status, token and
 * line are the API's; only counts and positions (`step k of j`, `{m} workflows`) are computed.
 */
import type { components } from '../../api/schema';
import { statusToken } from '../initiatives/format';

export type InitiativeDetail = components['schemas']['InitiativeDetailOut'];
export type DetailWorkflow = components['schemas']['DetailWorkflowOut'];
export type DetailStep = components['schemas']['DetailStepOut'];
type Project = components['schemas']['ProjectRead'];

export interface Selection {
  position: number;
  stepId: string | null;
}

export const statusTokenWord = statusToken;

export function stepStatusWord(status: DetailStep['status']): string {
  return status === 'waiting for her' ? 'needs you' : status;
}

export function isInteractive(w: DetailWorkflow): boolean {
  return w.type === 'interactive';
}

export function showNow(status: InitiativeDetail['status']): boolean {
  return status !== 'done' && status !== 'cancelled';
}

function attentionSuffix(d: InitiativeDetail): string {
  if (d.reason) return ` · ${d.reason}`;
  if (d.attention === 'your_turn') return ' · your turn';
  if (d.attention === 'answering' || d.attention === 'queued') return ' · agent answering';
  return '';
}

export function headerStateLine(d: InitiativeDetail): string {
  return `${statusToken(d.status).word} · ${d.workflow} · ${d.step}${attentionSuffix(d)}`;
}

export function headerPositionLine(d: InitiativeDetail): string {
  const base = `workflow ${d.current_position} of ${d.workflow_count} · ${d.workflow}`;
  const current = d.workflows.find((w) => w.position === d.current_position);
  if (!current || !isInteractive(current) || d.current_step === null) return base;
  const index = current.steps.findIndex((s) => s.id === d.current_step);
  if (index < 0) return base;
  return `${base} · step ${index + 1} of ${current.steps.length}`;
}

export function headerMetaLine(d: InitiativeDetail): string {
  const fixed = d.sequence_fixed_at ? `, fixed ${d.sequence_fixed_at.slice(0, 10)}` : '';
  const parts = [
    ...(d.hub ? [`hub ${d.hub.slug}`] : []),
    `folder ${d.folder}`,
    `package ${d.package} (${d.workflows.length} workflows${fixed})`,
    `created ${d.created_at}`,
  ];
  return parts.join(' · ');
}

export function workflowEyebrow(w: DetailWorkflow): string {
  return `WORKFLOW ${w.position} · ${isInteractive(w) ? 'INTERACTIVE' : 'AUTO'}`;
}

export function workflowMicro(w: DetailWorkflow): string {
  const base = `${w.template}@${w.version}`;
  return isInteractive(w) ? `${base} · ${w.steps.length} steps` : base;
}

export function stepEyebrow(position: number, k: number, kind: DetailStep['kind']): string {
  return `${position}.${k} · ${kind === 'conversation' ? 'CONVERSATION' : 'AUTOMATIC'}`;
}

export function stepAnnounce(k: number, step: DetailStep): string {
  return `${k} ${step.id}, ${stepStatusWord(step.status)}, ${step.line}`;
}

export function pollFast(d: InitiativeDetail): boolean {
  if (d.attention === 'answering' || d.attention === 'queued') return true;
  return d.runs.some((r) => r.status === 'queued' || r.status === 'running');
}

export function parseWorkflowParam(raw: string | null): number | null {
  if (raw === null || !/^[1-9]\d*$/.test(raw)) return null;
  return Number(raw);
}

export function defaultSelection(d: InitiativeDetail, initialWorkflow: number | null): Selection {
  const named = d.workflows.some((w) => w.position === initialWorkflow);
  const position = named && initialWorkflow !== null ? initialWorkflow : d.current_position;
  const workflow = d.workflows.find((w) => w.position === position);
  const inside =
    position === d.current_position &&
    (workflow?.steps.some((s) => s.id === d.current_step) ?? false);
  return { position, stepId: inside ? d.current_step : null };
}

export function previousWorkflowName(workflows: DetailWorkflow[], position: number): string | null {
  return workflows.find((w) => w.position === position - 1)?.workflow ?? null;
}

export function notStartedLines(
  w: DetailWorkflow,
  previous: string | null,
  project: Project | null,
): string[] {
  const lines = ['not started'];
  if (previous !== null) lines.push(`starts by itself when ${previous} is done`);
  lines.push(`template ${w.template}@${w.version} · auto`);
  if (project) {
    const budget = project.default_budget_usd
      ? `budget $${project.default_budget_usd}`
      : 'no default budget — the build will stop and ask';
    lines.push(
      `project defaults: autonomy ${project.default_autonomy ?? '—'} · ${project.default_model ?? '—'} · ${budget}`,
    );
  }
  return lines;
}
