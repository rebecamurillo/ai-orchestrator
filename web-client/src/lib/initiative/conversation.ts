/**
 * The pure helpers of the Initiative page's conversation column. Every line is fixed copy
 * around values the API sends (turn status, `n`, times, attention, reason, park reason, step
 * token and status); nothing here derives a status. Times are UTC.
 */
import type { components } from '../../api/schema';
import type { DetailStep, InitiativeDetail } from './page';

export type Turn = components['schemas']['TurnOut'];

export const QUEUED_CUT = 80;
const NOT_CLOSED = 'step not closed';

export function cut80(text: string): string {
  return text.slice(0, QUEUED_CUT);
}

function isoTime(iso: string | null): string {
  return iso === null ? '' : new Date(iso).toISOString();
}

export function turnTime(iso: string | null): string {
  return isoTime(iso).slice(11, 16);
}

export function clockSeconds(iso: string | null): string {
  return isoTime(iso).slice(11, 19);
}

function joined(parts: (string | null | undefined)[], sep = ' · '): string {
  return parts.filter((p): p is string => !!p).join(sep);
}

export function operatorAttribution(turn: Turn): string {
  return joined(['You', turnTime(turn.started_at)]);
}

export function agentAttribution(turn: Turn, step: DetailStep): string {
  return joined(['Agent', turn.model ?? step.model, turnTime(turn.ended_at)]);
}

export function conversationHead(step: DetailStep): string {
  return joined(['CONVERSATION', step.id.toUpperCase(), step.agent, step.harness, step.model]);
}

const turnsOf = (step: DetailStep): Turn[] => step.turns ?? [];
const filesOf = (step: DetailStep): string[] => (step.files ?? []).map((f) => f.path);

export function roundLine(step: DetailStep, detail: InitiativeDetail): string {
  const turns = turnsOf(step);
  const ended = turns.filter((t) => t.status === 'done' || t.status === 'failed').length;
  const round = turns.at(-1)?.round ?? detail.round;
  return `round ${round} · ${ended} ${ended === 1 ? 'turn' : 'turns'}`;
}

export function listedTurns(turns: Turn[]): Turn[] {
  return turns.filter((t) => t.status !== 'queued');
}

export function readOnlyTurns(turns: Turn[], showAll: boolean): Turn[] {
  return showAll ? turns : turns.slice(-3);
}

export function answeringLine(turn: Turn): string {
  return `agent answering turn ${turn.n} · started ${clockSeconds(turn.started_at)}`;
}

export function queuedLine(turn: Turn, waitsFor: number): string {
  return `queued · waits for turn ${waitsFor} to finish: "${cut80(turn.message)}"`;
}

export function queuedLines(turns: Turn[]): { turn: Turn; text: string }[] {
  const running = turns.find((t) => t.status === 'running');
  return turns
    .filter((t) => t.status === 'queued')
    .map((turn) => {
      const below = turns.filter((t) => t.status !== 'queued' && t.n < turn.n).map((t) => t.n);
      const waitsFor = running ? running.n : Math.max(0, ...below);
      return { turn, text: queuedLine(turn, waitsFor) };
    });
}

export function yourTurnLine(
  detail: InitiativeDetail,
  step: DetailStep,
  isCurrent: boolean,
): string | null {
  if (!isCurrent || detail.attention !== 'your_turn' || detail.reason !== '') return null;
  const last = listedTurns(turnsOf(step)).at(-1);
  return `your turn · turn ${last ? last.n + 1 : 1}`;
}

export function closedLine(
  step: DetailStep,
  next: DetailStep | null,
  slug: string,
): { text: string; next: string | null } | null {
  if (step.kind !== 'conversation' || step.token !== 'DON') return null;
  const paths = filesOf(step);
  const written = paths.length > 0 ? `${paths.join(', ')} written · ` : '';
  return {
    text: `step closed · ${written}committed on spec/${slug}`,
    next: next !== null && next.status !== 'planned' ? next.id : null,
  };
}

export function notClosedLine(step: DetailStep, isCurrent: boolean): string | null {
  const reason = step.park_reason;
  return isCurrent && reason && reason.startsWith(NOT_CLOSED) ? reason : null;
}

export function blockedLine(
  detail: InitiativeDetail,
  step: DetailStep,
  isCurrent: boolean,
): string | null {
  if (!isCurrent || detail.attention !== 'blocked' || notClosedLine(step, isCurrent) !== null) {
    return null;
  }
  if (listedTurns(turnsOf(step)).at(-1)?.status === 'failed') return null;
  return detail.reason ? `step blocked · ${detail.reason}` : 'step blocked';
}

export function isReadOnly(step: DetailStep): boolean {
  return step.token === 'DON' || step.token === 'SKP';
}

export function showsComposer(
  detail: InitiativeDetail,
  step: DetailStep,
  isCurrent: boolean,
): boolean {
  return (
    isCurrent &&
    step.park_kind === 'conversation' &&
    step.run_id !== null &&
    detail.status !== 'cancelled'
  );
}

export function closingHint(step: DetailStep): string {
  const paths = filesOf(step);
  const files = paths.length > 0 ? paths.join(', ') : step.file;
  return `Say you are done in your own words; the agent confirms in one line and writes ${files}. The step closes when the file holds its done content.`;
}

export function isSendKey(e: { key: string; ctrlKey: boolean; metaKey: boolean }): boolean {
  return e.key === 'Enter' && (e.ctrlKey || e.metaKey);
}
