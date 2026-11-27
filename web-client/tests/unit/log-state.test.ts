/** `lib/run/log-state.ts` (epic 2 story 4): the log panel's words per page state. */
import { describe, expect, it } from 'vitest';

import { logWords, notRunLine, showsDownload } from '../../src/lib/run/log-state';

const base = { reason: null, removed_at: null, lines: [] as string[] };

describe('logWords', () => {
  it('is null for text and for an absent state', () => {
    expect(logWords({ ...base, state: 'text', lines: ['a'] }, 0, 1)).toBeNull();
    expect(logWords({ ...base }, 0, 1)).toBeNull();
  });
  it('names a reason-less no_output', () => {
    expect(logWords({ ...base, state: 'no_output' }, 0, 1)).toBe(
      'no output · the command ran and printed nothing',
    );
  });
  it('names the reason of a no_output', () => {
    expect(logWords({ ...base, state: 'no_output', reason: 'no log was recorded' }, 0, 1)).toBe(
      'no output · no log was recorded',
    );
  });
  it('states the retention sweep with exit and duration', () => {
    const page = { ...base, state: 'removed' as const, removed_at: '2026-11-29T03:00:00Z' };
    expect(logWords(page, 1, 41.6)).toBe(
      'log removed by the retention sweep on 2026-11-29 · exit 1 · 42s were recorded',
    );
    expect(logWords(page, null, null)).toBe(
      'log removed by the retention sweep on 2026-11-29 · exit — · — were recorded',
    );
  });
  it('passes the backend line when removed_at is null', () => {
    expect(logWords({ ...base, state: 'removed', lines: ['log no longer on disk'] }, 1, 1)).toBe(
      'log no longer on disk',
    );
  });
});

describe('showsDownload', () => {
  it('is true for text, absent state and reason-less no_output only', () => {
    expect(showsDownload({ state: 'text', reason: null })).toBe(true);
    expect(showsDownload({ reason: null })).toBe(true);
    expect(showsDownload({ state: 'no_output', reason: null })).toBe(true);
    expect(showsDownload({ state: 'no_output', reason: 'x' })).toBe(false);
    expect(showsDownload({ state: 'removed', reason: null })).toBe(false);
  });
});

describe('notRunLine', () => {
  it('appends the reason when there is one', () => {
    expect(notRunLine('skipped · no command')).toBe('not run · skipped · no command');
    expect(notRunLine(null)).toBe('not run');
  });
});
