/**
 * The `#step-{seq}` fragment the Runs history links a row with (7.5, SPEC CAP-5, UX-DR14).
 *
 * A history row links to `/workflows/{run_id}#step-{seq}` (`lib/runs/history.ts::rowHref`),
 * and the Run detail has to land on that row rather than at the top of a table with fifty of
 * them. The browser cannot do it on its own: the Steps table is inside a `client:load`
 * island that renders nothing until its first fetch resolves (`RunDetail.tsx`), so by the
 * time the row exists the browser has long since given up on the fragment. `RunDetail.tsx`
 * scrolls to it itself, and these are the pure pieces of that — the id an anchored row
 * carries, the seq a fragment names, and how long the row stays promoted afterwards.
 *
 * Kept out of `lib/run/detail.ts`, which is already this component's longest lib module, and
 * out of the island, so both halves unit-test without a DOM (`vitest.config.ts` runs in
 * `environment: 'node'`).
 */

/** How long an anchored row stays promoted before it reads like every other row.
 * "Promoted briefly" (binding rule): long enough to find the row after the scroll, short
 * enough that a screen left open does not keep asserting where the Operator arrived. */
export const PROMOTED_MS = 4_000;

/** The `id` the Steps table gives row `seq`, and the fragment a history row links with. */
export function stepAnchorId(seq: number): string {
  return `step-${seq}`;
}

/**
 * The `seq` a location fragment names, or `null` for anything that is not one of ours.
 *
 * Deliberately strict: only `#step-` followed by digits. A fragment is user-supplied text —
 * it survives copy-paste, hand-editing and stale links — so `#step-` alone, `#step-7x`,
 * `#step--1` and `#steps` all answer `null` rather than a number that would then be looked
 * up as an element id. `Number()` alone would accept `" 7"`, `"7e2"` and `"0x7"`.
 */
export function anchoredSeq(hash: string): number | null {
  const match = /^#step-(\d+)$/.exec(hash);
  return match ? Number(match[1]) : null;
}
