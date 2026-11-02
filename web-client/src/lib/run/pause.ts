/**
 * The *Pause* control's own facts (story 2-1, CAP-8, NFR-8): when a running Run offers it, and
 * the sentences that state what it does before and after it is sent.
 *
 * `admitted_signals` still decides: a running Run lists `pause` until one is requested, so the
 * button appears exactly where the server says the signal applies.
 */
import type { SignalKind } from './detail';

export const PAUSE_LABEL = 'Pause';
export const PAUSE_CONFIRM_LABEL = 'Pause run';
export const PAUSE_KEEP_LABEL = 'Keep running';

/** What confirming does, in mechanism: nothing is killed and the stop is before the next row. */
export const PAUSE_CONFIRM_LINE =
  'pause run: the current step finishes, nothing is killed, and the run stops before the next row until you continue or cancel';

/** What a run with a request pending states in place of the button. */
export const PAUSE_REQUESTED_LINE =
  'pause requested: the run stops before the next row when the current step ends';

export function offersPause(admitted: readonly SignalKind[]): boolean {
  return admitted.includes('pause');
}
