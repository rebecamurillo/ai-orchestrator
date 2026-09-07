/**
 * The Board's last successfully-fetched read model (SPEC CAP-14). `Board.tsx` is the one
 * writer; `AppRail`/`FooterReadout` cannot subscribe themselves (they are `.astro`,
 * container-tested with no framework renderer registered — see `Board.tsx`'s own module
 * doc), so `Board.tsx` reads this store back out in the same effect that wrote it, purely so
 * the rail/footer DOM-sync and the column rendering share one source of truth instead of two
 * copies of the same `BoardOut`.
 *
 * `null` until the first successful fetch — never a synthetic empty `BoardOut`, so a
 * subscriber can tell "nothing fetched yet" from "fetched, and it was empty".
 */
import { atom } from 'nanostores';

import type { components } from '../api/schema';

export type BoardOut = components['schemas']['BoardOut'];

export const $board = atom<BoardOut | null>(null);

export function setBoard(data: BoardOut): void {
  $board.set(data);
}

/** Back to "nothing fetched yet" — the reset a test suite needs between cases (`template-
 * validation.ts`'s own `resetTemplateValidation` is the precedent). */
export function clearBoard(): void {
  $board.set(null);
}
