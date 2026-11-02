/**
 * The Operator's senior session as the Run page reads and drives it (story 2-4, SPEC CAP-7):
 * when the offer shows, what the start, the close and a message post, and how a turn reads.
 *
 * The lock is the server's. While a session is open `admitted_signals` is `cancel` and
 * `session_end`, so the page hides the stop's other controls by rendering what that list
 * admits, and nothing here re-derives the rule.
 */
import type { components } from '../../api/schema';
import type { SignalIn, SignalKind } from './signals';

export type SessionOut = components['schemas']['SessionOut'];
export type SessionTurn = components['schemas']['SessionTurnOut'];
export type AnchorEdit = components['schemas']['AnchorEditOut'];
export type SessionScope = SessionOut['scopes'][number];
export type HarnessOut = components['schemas']['HarnessOut'];
export type ProbeResultOut = components['schemas']['ProbeResultOut'];
type ProblemDetail = components['schemas']['ProblemDetail'];
type MessageIn = components['schemas']['MessageIn'];

export const SESSION_LABEL = 'Senior session';
export const START_LABEL = 'Start session';
export const DISMISS_LABEL = 'Dismiss';
export const CLOSE_LABEL = 'Close session';
export const CLOSE_CONFIRMED_LABEL = 'Close with confirmed files';
export const SEND_LABEL = 'Send';
export const CONFIRM_LABEL = 'Confirm';
export const REVERT_LABEL = 'Revert';
export const NO_REPLY_LINE = 'no reply file';
export const LOG_LINK_LABEL = 'log';
export const HARNESS_DEFAULT_LABEL = 'harness default';

export const OFFER_LINE =
  'senior session: a coding agent works in this Run’s worktree in conversation, commits each turn as "session: turn n" and bills the Run';
export const LOCK_LINE =
  'senior session open · Answer, Retry, Continue and Skip are disabled until Close session · Cancel run stays available';
export const NO_HARNESS_LINE = 'no harness is enabled';
export const ANCHOR_LINE =
  'anchor files this session changed: confirm each one or ask the senior to revert it, then close';
export const NO_ANCHOR_LINE = 'no anchor edit remains';
export const ANCHOR_BUSY_LINE = 'a turn is running; confirm and revert resume when it ends';

/** `scope` is the stop's frame the senior reads: the words say which one. */
export const SCOPE_LABELS: Record<SessionScope, string> = {
  story: 'story',
  epic: 'epic',
  run: 'Run',
};

const SESSION_START: SignalKind = 'session_start';
const SESSION_END: SignalKind = 'session_end';

export function turnRunningLine(turn: number): string {
  return `turn ${turn} is running; the message box is disabled until it ends`;
}

export function turnFailedLine(exitCode: number | null): string {
  return exitCode === null ? 'turn ended in error' : `turn ended in error · exit ${exitCode}`;
}

/** The offer shows where the server says a start would pass, and no session is open. */
export function offersSession(session: SessionOut | null): boolean {
  return session !== null && session.available && !session.active;
}

/** A session is open when the read says so or the server admits its close. */
export function sessionOpen(session: SessionOut | null, admitted: readonly SignalKind[]): boolean {
  return (session?.active ?? false) || admitted.includes(SESSION_END);
}

/** The narrowest scope the stop has, which is the first the server lists. */
export function defaultScope(scopes: readonly SessionScope[]): SessionScope | '' {
  return scopes[0] ?? '';
}

export function startableHarnesses(harnesses: readonly HarnessOut[]): HarnessOut[] {
  return harnesses.filter((harness) => harness.enabled);
}

/** A model survives a harness change only if the new probe lists it; a harness that lists
 * none takes a typed name, which is kept. */
export function reconcileModel(model: string, models: readonly string[]): string {
  if (models.length === 0) return model;
  return models.includes(model) ? model : '';
}

interface StartState {
  scope: SessionScope | '';
  harness: string;
  probe: ProbeResultOut | null;
  probing: boolean;
  posting: boolean;
}

export function canStart({ scope, harness, probe, probing, posting }: StartState): boolean {
  return scope !== '' && harness !== '' && probe?.ok === true && !probing && !posting;
}

/** `model` is omitted when blank: the server then leaves the harness on its default. */
export function startBody(scope: SessionScope, harness: string, model: string): SignalIn {
  const payload: Record<string, string> = { scope, harness };
  if (model) payload.model = model;
  return { kind: SESSION_START, payload };
}

export function endBody(confirmedPaths: readonly string[]): SignalIn {
  if (confirmedPaths.length === 0) return { kind: SESSION_END };
  return { kind: SESSION_END, payload: { confirmed_paths: [...confirmedPaths] } };
}

/** A refused close opens the anchor review when the session lists edits. The list is the
 * server's structured fact; the refusal's sentence is shown to the Operator, not parsed. */
export function opensReview(refusal: ProblemDetail | null, session: SessionOut | null): boolean {
  return refusal !== null && (session?.anchor_edits.length ?? 0) > 0;
}

export function toggleConfirmed(confirmed: ReadonlySet<string>, path: string): Set<string> {
  const next = new Set(confirmed);
  if (!next.delete(path)) next.add(path);
  return next;
}

/** Only files the session still lists can be confirmed: the server refuses any other. */
export function confirmedFor(
  edits: readonly AnchorEdit[],
  confirmed: ReadonlySet<string>,
): string[] {
  return edits.map((edit) => edit.path).filter((path) => confirmed.has(path));
}

export function allConfirmed(
  edits: readonly AnchorEdit[],
  confirmed: ReadonlySet<string>,
): boolean {
  return edits.every((edit) => confirmed.has(edit.path));
}

export function revertMessage(path: string): string {
  return `Revert ${path} to its state before this session, then say when it is restored.`;
}

export function messageBody(text: string): MessageIn {
  return { text: text.trim() };
}

export function canSend(session: SessionOut | null, draft: string, posting: boolean): boolean {
  return session !== null && !session.turn_running && !posting && draft.trim().length > 0;
}

export type TurnState = 'running' | 'replied' | 'no_reply' | 'failed';

/** A turn is busy until it is committed, which is when `ended_at` is written. */
export function turnState(turn: SessionTurn): TurnState {
  if (turn.ended_at === null || turn.status === 'queued' || turn.status === 'running') {
    return 'running';
  }
  if (turn.status === 'error') return 'failed';
  return turn.reply === '' ? 'no_reply' : 'replied';
}

export function logHref(runId: string, attemptId: string): string {
  return `/api/runs/${runId}/attempts/${attemptId}/log`;
}

export function sessionRequestPath(runId: string): string {
  return `/api/runs/${runId}/session`;
}

export function messagesRequestPath(runId: string): string {
  return `/api/runs/${runId}/session/messages`;
}

/** A parked Run polls slowly unless a turn is running, and the box must re-enable promptly. */
export function keepsFastPoll(runStatus: string, session: SessionOut | null): boolean {
  return runStatus === 'running' || (session?.turn_running ?? false);
}
