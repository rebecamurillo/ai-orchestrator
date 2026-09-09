/**
 * The terminal resume block's own pure derivations (6.7, FR-21, UX-DR5, UX-DR9).
 *
 * Kept out of `CommandBlock.tsx` for `web-client/AGENTS.md`'s reason — a rule that unit-tests
 * without a DOM — and out of `detail.ts` for the reason `skip.ts` and `accept.ts` are their
 * own files: that module's `stopSignals`/`blockedSignals`/`checkpointSignals` are frozen, and
 * a control is appended through a sibling filter rather than by widening one of them.
 *
 * **Nothing here builds or edits the command.** `detail.run.terminal.command` is the server's,
 * verbatim, and it is rendered as text — never as markup, and never re-assembled in the
 * browser from parts. That is AD-5's half of this screen: the string the backend proved
 * carries no secret value is the string the operator sees and copies, byte for byte.
 */
import type { components } from '../../api/schema';
import type { RunDetailOut, SignalKind } from './detail';

export type TerminalOut = components['schemas']['TerminalOut'];

/** The section head, as UX-DR5 names it. */
export const COMMAND_EYEBROW = 'OR CONTINUE IN THE SESSION';
/** The Copy button's two words: what it says, and what it says for ~1.2 s after a click. */
export const COPY_LABEL = 'COPY';
export const COPIED_LABEL = 'COPIED';
/** How long `COPIED` stands before the button reads `COPY` again (the brief's "~1.2 s"). */
export const COPIED_MS = 1200;

/** The control that ends a session, and the line above it (EXPERIENCE-v1 §2.2, verbatim). */
export const RELEASE_LABEL = 'Release';
export const TERMINAL_SESSION_LINE =
  'terminal session in progress · Answer, Continue, Skip and Retry disabled until Release — ' +
  'the run resumes by itself when the story file is done and the tree is clean';

/** The signal each control posts. */
export const TERMINAL_START: SignalKind = 'terminal_start';
export const TERMINAL_RELEASE: SignalKind = 'terminal_release';

/**
 * The block to render, or `null` when this Run has none — a park the escape hatch does not
 * apply to, a harness that cannot resume, or a `local` attempt (`application/use_cases/
 * terminal.py` owns the whole list). Optional on the wire (`_drop_default`-guarded), so a
 * fixture written before this story reads as "no terminal" rather than throwing.
 */
export function terminalBlock(detail: RunDetailOut): TerminalOut | null {
  return detail.run.terminal ?? null;
}

/** `session lifetime ends {date}`, or `''` when the harness states no lifetime. */
export function sessionLifetimeLine(endsAt: string | null | undefined): string {
  if (!endsAt) return '';
  return `session lifetime ends ${endsAt}`;
}

/**
 * `admitted_signals`, narrowed to the terminal controls the button row appends — today only
 * `terminal_release`, and only while the server says a session is open. A sibling of
 * `stopSignals`/`blockedSignals`/`checkpointSignals`, never a widening of one: each of those
 * is frozen by a test that predates this story.
 *
 * The server is still what decides. While a session is open `run_admitted_signals` answers
 * `['cancel', 'terminal_release']` and the endpoint refuses everything else with a 409, so a
 * screen that renders this list can offer nothing the server would not apply.
 */
export function terminalSignals(admitted: readonly SignalKind[]): SignalKind[] {
  return admitted.filter((kind) => kind === TERMINAL_RELEASE);
}

/** Whether the server admits a Release right now — what decides the button, so the control
 * comes off `admitted_signals` rather than off the block's own `in_progress`. The two agree
 * in practice; where they ever did not, the line still states the session and the row offers
 * only what the endpoint would apply. */
export function offersRelease(admitted: readonly SignalKind[]): boolean {
  return terminalSignals(admitted).length > 0;
}
