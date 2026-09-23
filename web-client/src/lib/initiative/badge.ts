/**
 * The initiative badge a Run carries once it was dispatched as one of an initiative's
 * members (S7): `{slug} · {role}`, linking to `/workflows/initiative/{slug}`. Reads only
 * the two stored fields every read model carries them on — `initiative` and
 * `initiative_role` — never a Template name (S7's own rule: "DO NOT add template-name
 * string matching anywhere").
 *
 * **`CardOut` carries both fields too (S8).** The Board's read model (`RunCard.tsx`/
 * `RunListRow.tsx`) was widened alongside the run detail's own `RunDetailSummaryOut`
 * (`RunDetailOut.run`, read by `Header.tsx`) — the same two fields, so this one function
 * serves every caller through the structural `InitiativeCarrier` shape below rather than a
 * union import list that would grow every time another read model gains them.
 */

/** The minimal shape either read model carries — structural rather than importing
 * `RunSummaryOut`/`RunDetailSummaryOut` outright, so this one function serves both without
 * a union import list growing every time a third read model gains the same two fields. */
export interface InitiativeCarrier {
  initiative?: string | null;
  initiative_role?: ('epic' | 'merge' | 'golive') | null;
}

/** `{slug} · {role}` — `null` for a Run that is not an initiative member at all, so a caller
 * renders the badge only when there is one. `role` reads `'—'` for the one case the wire
 * allows a slug with no role (`initiative_role` is independently optional). */
export function initiativeBadgeText(run: InitiativeCarrier): string | null {
  if (!run.initiative) return null;
  return `${run.initiative} · ${run.initiative_role ?? '—'}`;
}

export function initiativeHref(slug: string): string {
  return `/workflows/initiative/${encodeURIComponent(slug)}`;
}
