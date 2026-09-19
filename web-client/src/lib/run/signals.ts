/**
 * The `POST /runs/{id}/signals` body each control on the Run detail posts (4.9's own
 * contract, SPEC CAP-15). Kept beside `detail.ts` rather than inside it: this half builds a
 * *request*, that half reads a *response* — the same split `src/lib/newwf/state.ts`
 * (`preflightBody`/`runBody`) draws for the New workflow screen.
 */
import type { components } from '../../api/schema';

export type SignalKind = components['schemas']['SignalIn']['kind'];
export type SignalIn = components['schemas']['SignalIn'];

/** `Continue`/`Retry` carry no payload; `Cancel run`'s confirm is the one control in this
 * epic that does (`{confirm: true}` — the binding rule's own body). */
export function signalBody(kind: SignalKind): SignalIn {
  if (kind === 'cancel') return { kind, payload: { confirm: true } };
  return { kind };
}

/** The request path `FailedFetch`-shaped 409 readouts show. */
export function signalsRequestPath(runId: string): string {
  return `/api/runs/${runId}/signals`;
}

/** The word a button reads for one signal kind — `Continue`, `Retry`, `Cancel run`, and
 * (5.10) `Skip story`/`Skip epic` for a `blocked`/`misconfigured` stop's own row. */
export function signalLabel(kind: SignalKind): string {
  if (kind === 'continue') return 'Continue';
  if (kind === 'retry') return 'Retry';
  if (kind === 'cancel') return 'Cancel run';
  if (kind === 'skip_story') return 'Skip story';
  if (kind === 'skip_epic') return 'Skip epic';
  return kind;
}

/** `POST /runs/{id}/signals`'s body for a mode-aware Retry (story 3-4).
 * `mode` is `'restart'` or `'session'` — the delivery mode the Operator chose. */
export function retryBody(mode: string): SignalIn {
  return { kind: 'retry', payload: { mode } };
}
