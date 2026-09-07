/**
 * `src/stores/board.ts` (4.14): the Board's last successfully-fetched `BoardOut`. `null`
 * until the first fetch, so a subscriber can tell "nothing fetched yet" from "fetched, and
 * it was empty" — `template-validation.ts`'s own reasoning for starting `null`.
 */
import { afterEach, describe, expect, it } from 'vitest';

import { $board, clearBoard, setBoard } from '../../src/stores/board';
import type { BoardOut } from '../../src/lib/board/format';

const SAMPLE: BoardOut = {
  columns: { queued: [], running: [], needs_you: [], done: [], failed: [] },
  counts: { queued: 0, running: 0, needs_you: 0 },
  generated_at: '2026-01-01T00:00:00Z',
};

afterEach(() => clearBoard());

describe('$board', () => {
  it('starts at null — nothing fetched yet', () => {
    expect($board.get()).toBeNull();
  });

  it('setBoard publishes the fetched data', () => {
    setBoard(SAMPLE);
    expect($board.get()).toEqual(SAMPLE);
  });

  it('clearBoard resets to null', () => {
    setBoard(SAMPLE);
    clearBoard();
    expect($board.get()).toBeNull();
  });
});
