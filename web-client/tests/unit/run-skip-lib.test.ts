/**
 * `src/lib/run/skip.ts` (6.4, FR-11, FR-20, NFR-8): which stops offer *Skip story*, the
 * confirm sentence, and the `done` Run's compare line.
 *
 * The confirm line is asserted character for character, because it is the one place the
 * screen states what the signal will do to the branch — including the exact commit message
 * the leftovers land under (`signal_effects.py::SKIP_MESSAGE`).
 */
import { describe, expect, it } from 'vitest';

import type { RunDetailOut, SignalKind } from '../../src/lib/run/detail';
import {
  KEEP_LABEL,
  SKIP_STORY_LABEL,
  SKIP_STORY_STOP_KINDS,
  compareLinkText,
  offersSkipStory,
  skipStoryConfirmLine,
  skippedIds,
} from '../../src/lib/run/skip';

const ADMITTED: SignalKind[] = ['skip_story', 'skip_epic', 'cancel'];
const STORY = '4-3';

function detail(summary: RunDetailOut['summary']): RunDetailOut {
  return { summary } as unknown as RunDetailOut;
}

describe('offersSkipStory', () => {
  it('offers the action on exactly the seven bodies FR-20 lists', () => {
    expect([...SKIP_STORY_STOP_KINDS]).toEqual([
      'blocked',
      'checkpoint',
      'verify_failed',
      'timeout',
      'protected_path',
      'misconfigured',
      'internal',
    ]);
    for (const kind of SKIP_STORY_STOP_KINDS) {
      expect(offersSkipStory(kind, ADMITTED, STORY)).toBe(true);
    }
  });

  it('never offers it where the server did not admit it', () => {
    expect(offersSkipStory('verify_failed', ['retry', 'skip_epic', 'cancel'], STORY)).toBe(false);
    expect(offersSkipStory('blocked', [], STORY)).toBe(false);
  });

  it('never offers it on a body outside the list, or on no stop at all', () => {
    expect(offersSkipStory('push_rejected', ADMITTED, STORY)).toBe(false);
    expect(offersSkipStory('plan_stale', ADMITTED, STORY)).toBe(false);
    expect(offersSkipStory('budget', ADMITTED, STORY)).toBe(false);
    expect(offersSkipStory('failed', ADMITTED, STORY)).toBe(false);
    expect(offersSkipStory(null, ADMITTED, STORY)).toBe(false);
  });

  it('never offers it when the response names no Story to skip', () => {
    // the client-side twin of `_has_story_frame`: a park outside every story frame is the
    // 409 `validate` would answer, and a confirm there could name no id at all
    expect(offersSkipStory('internal', ADMITTED, '')).toBe(false);
  });
});

describe('skipStoryConfirmLine', () => {
  it('states the mechanism verbatim, naming the commit message', () => {
    expect(skipStoryConfirmLine('4-3')).toBe(
      'skip story 4-3: its remaining steps are marked skipped, the quality gate re-runs, ' +
        'leftovers are committed as "story 4-3: skipped by operator"',
    );
  });

  it('names no invented id when the response carries no current story', () => {
    expect(skipStoryConfirmLine('')).toContain('skip story this story:');
  });

  it('labels the two buttons the brief names', () => {
    expect(SKIP_STORY_LABEL).toBe('Skip story');
    expect(KEEP_LABEL).toBe('Keep');
  });
});

describe('compareLinkText / skippedIds', () => {
  it('names the skipped ids beside the url', () => {
    const d = detail({ progress: null, links: ['https://a'], skipped: ['2', '4-3'] });

    expect(compareLinkText(d, 'https://a')).toBe('https://a · skipped: 2, 4-3');
    expect(skippedIds(d)).toEqual(['2', '4-3']);
  });

  it('leaves the url alone when nothing was skipped', () => {
    const d = detail({ progress: null, links: ['https://a'], skipped: [] });

    expect(compareLinkText(d, 'https://a')).toBe('https://a');
  });

  it('leaves it alone before the Run is done and has a summary at all', () => {
    const d = detail(null);

    expect(compareLinkText(d, 'https://a')).toBe('https://a');
    expect(skippedIds(d)).toEqual([]);
  });
});
