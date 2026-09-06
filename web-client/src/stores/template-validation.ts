/**
 * The channel `TemplateEditor` publishes each validation outcome to, and the diagram reads
 * (3.6).
 *
 * The two islands sit in two different grid cells of the Templates screen, so they cannot
 * share React state, and the editor's text lives in a ref precisely so a keystroke does not
 * re-render it. A nanostore is what `web-client/AGENTS.md` names as this component's
 * cross-island mechanism; `nanostores` and `@nanostores/react` are already dependencies, and
 * unlike a DOM `CustomEvent` a store is testable in `environment: 'node'`.
 *
 * The editor publishes *text and validity*, never a graph: fetching the graph belongs to the
 * column that draws it, which keeps the editor's job unchanged.
 *
 * `seq` counts up and is what makes two identical outcomes two distinguishable values. Two
 * validations of the same text after a failed one must both be seen, or `useStore` would
 * treat the second as no change and the stale line would never clear.
 */
import { atom } from 'nanostores';

export interface ValidationOutcome {
  /** Monotonic, from 1. Two identical outcomes differ here and nowhere else. */
  seq: number;
  /** Exactly the text that was validated — never the text typed since. */
  yaml: string;
  /** Whether the validator reported no errors. `unvalidated` paths are not errors (NFR-2). */
  ok: boolean;
}

/** `null` until the first Validate: a diagram mounted before one draws its own initial graph. */
export const $templateValidation = atom<ValidationOutcome | null>(null);

/** Publish one outcome, and hand back the value that was published. */
export function publishValidation(outcome: { yaml: string; ok: boolean }): ValidationOutcome {
  const published: ValidationOutcome = {
    seq: ($templateValidation.get()?.seq ?? 0) + 1,
    yaml: outcome.yaml,
    ok: outcome.ok,
  };
  $templateValidation.set(published);
  return published;
}

/**
 * Back to "nothing has been validated yet". The store outlives a single test the way it
 * outlives a single island, so a suite that did not reset it would read the previous test's
 * last outcome.
 */
export function resetTemplateValidation(): void {
  $templateValidation.set(null);
}
