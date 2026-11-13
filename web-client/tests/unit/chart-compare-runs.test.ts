import { describe, expect, it } from 'vitest';

import {
  FOLLOWING,
  NOT_SPLIT_LINE,
  NO_SUCH_STEP,
  SCROLL_RUNS,
  keyEntries,
  runNames,
  sharedWords,
} from '../../src/lib/charts/compare-runs';
import { A, B, header } from './metrics-compare-fixtures';

describe('compare run identity', () => {
  it('prints the fixed wording', () => {
    expect(FOLLOWING('x')).toBe('following: x · click again to stop');
    expect(NOT_SPLIT_LINE).toBe(
      'not split by role: machine time, waiting on you, your interventions, budget, every static signal on the change',
    );
    expect(NO_SUCH_STEP).toBe('no such step in this template');
    expect(SCROLL_RUNS).toBe(15);
  });

  it('finds the words every label shares, in the first label order', () => {
    expect(sharedWords(['familio snake-v2 opus', 'familio snake-v2 sonnet'])).toEqual([
      'familio',
      'snake-v2',
    ]);
    expect(sharedWords(['only one'])).toEqual([]);
    expect(sharedWords([])).toEqual([]);
    expect(sharedWords(['a b', 'c d'])).toEqual([]);
  });

  it('names a Run by position, the label without shared words, and its short id', () => {
    const names = runNames([
      header(A, { label: 'familio snake-v2 opus' }),
      header(B, { label: 'familio snake-v2 sonnet' }),
    ]);
    expect(names[0]).toMatchObject({ runId: A, position: 'R1', label: 'familio snake-v2 opus' });
    expect(names[0].lines).toEqual(['opus', A.slice(0, 8)]);
    expect(names[1].position).toBe('R2');
    expect(names[1].lines).toEqual(['sonnet', B.slice(0, 8)]);
  });

  it('keeps the full label when nothing remains after the shared words', () => {
    const names = runNames([
      header(A, { label: 'same label' }),
      header(B, { label: 'same label' }),
    ]);
    expect(names[0].lines).toEqual(['same label', A.slice(0, 8)]);
  });

  it('builds key entries, collapsing a blind label', () => {
    expect(keyEntries([header(A, { label: 'one' })])).toEqual([`R1 · one · ${A.slice(0, 8)}`]);
    expect(keyEntries([header(A, { label: 'R1' }), header(B, { label: 'R2' })])).toEqual([
      `R1 · ${A.slice(0, 8)}`,
      `R2 · ${B.slice(0, 8)}`,
    ]);
  });
});
