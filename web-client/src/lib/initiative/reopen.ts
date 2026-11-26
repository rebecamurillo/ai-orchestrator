/**
 * The pure rules of the reopen control: where it shows, the spec steps it offers, and the
 * lines of its modal. Status, reason and Run states are the API's; only fixed copy is composed.
 */
import { shortId } from './files';
import { isInteractive, type DetailStep, type DetailWorkflow, type InitiativeDetail } from './page';
import { stopBanner } from './stops';

type DetailRun = InitiativeDetail['runs'][number];

export type ReopenOrigin = 'build' | 'advance';
export type ReopenPlacement = 'banner' | 'summary' | null;

export const REOPEN_HEAD = 'REOPEN A SPEC STEP';
export const KEEP_LABEL = 'Keep the build stopped';

export function latestRun(d: InitiativeDetail): DetailRun | null {
  let best: DetailRun | null = null;
  for (const r of d.runs ?? []) {
    if (!best || r.created_at > best.created_at) best = r;
  }
  return best;
}

export function liveRun(d: InitiativeDetail): DetailRun | null {
  const live = (d.runs ?? []).filter(
    (r) => r.status === 'queued' || r.status === 'running' || r.status === 'needs_you',
  );
  return live.reduce<DetailRun | null>(
    (best, r) => (!best || r.created_at > best.created_at ? r : best),
    null,
  );
}

export function reopenPlacement(d: InitiativeDetail, selectedPosition: number): ReopenPlacement {
  if (stopBanner(d, selectedPosition)?.kind === 'advance') return 'banner';
  if (d.status !== 'waiting for her' && d.status !== 'failed') return null;
  const w = d.workflows.find((x) => x.position === selectedPosition);
  if (!w || isInteractive(w) || !w.run_id) return null;
  return w.run_id === latestRun(d)?.id ? 'summary' : null;
}

export function specWorkflow(d: InitiativeDetail): DetailWorkflow | null {
  return (
    d.workflows.find((w) => isInteractive(w) && w.steps.some((s) => s.kind === 'conversation')) ??
    null
  );
}

export function reopenSteps(d: InitiativeDetail): { id: string; label: string }[] {
  const w = specWorkflow(d);
  if (!w) return [];
  return w.steps.flatMap((s, i) =>
    s.kind === 'conversation'
      ? [
          {
            id: s.id,
            label: `${s.number || `${w.position}.${i + 1}`} ${s.id}${s.agent ? ` · ${s.agent}` : ''}`,
          },
        ]
      : [],
  );
}

export function reopenReason(
  d: InitiativeDetail,
  origin: ReopenOrigin,
  runId: string | null,
): string {
  if (origin === 'advance') return `advance blocked: ${d.reason}`;
  return `build stopped: ${d.reason || `Run ${shortId(runId ?? '')} failed`}`;
}

export function reopenQuestion(origin: ReopenOrigin): string {
  return origin === 'build'
    ? 'Which spec step does this build stop come from?'
    : 'Which spec step does this stop come from?';
}

export function reopenRunId(
  d: InitiativeDetail,
  origin: ReopenOrigin,
  selectedRunId: string | null,
): string | null {
  return origin === 'build' ? selectedRunId : (liveRun(d)?.id ?? null);
}

export function reopenMechanism(
  d: InitiativeDetail,
  runId: string | null,
  step: string | null,
): string {
  const cancelled = runId ? `Run ${shortId(runId)} is cancelled and keeps its page. ` : '';
  return `${cancelled}${step ?? 'The step you choose'} reopens as round ${d.round + 1} with this stop as its first turn, on spec/${d.slug}, created from main if it was deleted after the merge. Then the gate, the merge and the build run again.`;
}

export function reopenLabel(step: string | null): string {
  return step === null ? 'Reopen step' : `Reopen ${step}`;
}

export function freshBranchLine(step: DetailStep, slug: string): string | null {
  return step.reopened_after?.branch === 'created' ? `on a fresh spec/${slug} from main` : null;
}
