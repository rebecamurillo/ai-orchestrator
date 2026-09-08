/**
 * `src/lib/run/detail.ts`'s 5.10 additions: `questionEyebrow`, `misconfiguredFiles`, and
 * `blockedSignals` — kept apart from the frozen `run-detail-lib.test.ts`, which predates all
 * three and whose own `hasEffect`/`stopSignals` assertions this story must not touch.
 */
import { describe, expect, it } from 'vitest';

import {
  blockedSignals,
  misconfiguredFiles,
  questionEyebrow,
  type AttributionOut,
} from '../../src/lib/run/detail';

describe('questionEyebrow', () => {
  it('joins harness, model and ended_at with the eyebrow separator', () => {
    const attribution: AttributionOut = {
      harness: 'claude',
      model: 'claude-opus-4',
      ended_at: '2026-09-07T09:05:00Z',
    };

    expect(questionEyebrow(attribution)).toBe(
      'Agent · claude · claude-opus-4 · 2026-09-07T09:05:00Z',
    );
  });

  it('reads em dashes for missing parts', () => {
    expect(questionEyebrow({ harness: null, model: null, ended_at: null })).toBe(
      'Agent · — · — · —',
    );
  });

  it('reads em dashes throughout for no attribution at all', () => {
    expect(questionEyebrow(null)).toBe('Agent · — · — · —');
    expect(questionEyebrow(undefined)).toBe('Agent · — · — · —');
  });
});

describe('misconfiguredFiles', () => {
  it('splits the ambiguous-story-file condition into a file list', () => {
    expect(misconfiguredFiles('ambiguous story file: 1-a.md, 1-b.md')).toEqual([
      '1-a.md',
      '1-b.md',
    ]);
  });

  it('is empty for a condition that names no files', () => {
    expect(misconfiguredFiles('no story file')).toEqual([]);
    expect(misconfiguredFiles('harness misconfigured: no subagents')).toEqual([]);
    expect(misconfiguredFiles('unexpected status: draft')).toEqual([]);
    expect(misconfiguredFiles('harness exit 1')).toEqual([]);
    expect(misconfiguredFiles('gateway unreachable')).toEqual([]);
  });

  it('is empty for null or undefined', () => {
    expect(misconfiguredFiles(null)).toEqual([]);
    expect(misconfiguredFiles(undefined)).toEqual([]);
  });
});

describe('blockedSignals', () => {
  it('keeps retry and the two skips, in the admitted order', () => {
    expect(blockedSignals(['retry', 'skip_story', 'skip_epic', 'cancel'])).toEqual([
      'retry',
      'skip_story',
      'skip_epic',
    ]);
  });

  it('never admits answer, even when the read model carries it', () => {
    expect(blockedSignals(['answer', 'skip_story', 'skip_epic', 'cancel'])).toEqual([
      'skip_story',
      'skip_epic',
    ]);
  });

  it('is empty when nothing admitted has any effect here', () => {
    expect(blockedSignals(['cancel'])).toEqual([]);
  });
});
