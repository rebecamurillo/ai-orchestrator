/**
 * `src/lib/board/format.ts` (4.14): every pure computation the Board renders from a
 * `BoardOut` — age text, the aged-signal rule, the progress segment, the two readouts, the
 * `done`/`failed` bound, and the failed-fetch command line.
 */
import { describe, expect, it } from 'vitest';

import {
  ageText,
  boardRequestPath,
  capColumn,
  clockText,
  fetchFailureMessage,
  footerReadoutText,
  hasLeftRule,
  isAgedNeedsYou,
  moreNotShownText,
  oldestWaitSeconds,
  progressText,
  surfaceReadoutText,
  tokenSignal,
  totalCards,
  type BoardOut,
  type CardOut,
} from '../../src/lib/board/format';

function card(overrides: Partial<CardOut> = {}): CardOut {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    token: 'RUN',
    status: 'running',
    park_kind: null,
    branch: 'epics/1',
    project_name: 'demo',
    repository_slug: 'demo-repo',
    current_step_label: 'epic 1 · story 3-2 · build',
    harness: null,
    template: 'initiative',
    version: 1,
    progress: { epics_done: 1, epics_total: 2, stories_done: 5, stories_total: 8, links: 1 },
    kind_label: null,
    age_seconds: 60,
    needs_you_since: null,
    ...overrides,
  };
}

describe('ageText', () => {
  it('renders minutes under an hour', () => {
    expect(ageText(90)).toBe('1m');
  });

  it('renders hours and minutes under a day', () => {
    expect(ageText(3 * 3600 + 7 * 60)).toBe('3h 07m');
  });

  it('renders days and hours at a day or more', () => {
    expect(ageText(2 * 86400 + 4 * 3600)).toBe('2d 04h');
  });

  it('never goes negative', () => {
    expect(ageText(-5)).toBe('0m');
  });
});

describe('isAgedNeedsYou', () => {
  it('is true for a BLK card older than 48h', () => {
    expect(isAgedNeedsYou('BLK', 48 * 3600 + 1)).toBe(true);
  });

  it('is true for a CHK card older than 48h', () => {
    expect(isAgedNeedsYou('CHK', 49 * 3600)).toBe(true);
  });

  it('is false for a BLK card at or under 48h', () => {
    expect(isAgedNeedsYou('BLK', 48 * 3600)).toBe(false);
  });

  it('is false for any other token, however old', () => {
    expect(isAgedNeedsYou('ERR', 100 * 3600)).toBe(false);
  });
});

describe('tokenSignal', () => {
  it('maps RUN to run, BLK/CHK to needs-you, ERR to failed, everything else neutral', () => {
    expect(tokenSignal('RUN')).toBe('run');
    expect(tokenSignal('BLK')).toBe('needs-you');
    expect(tokenSignal('CHK')).toBe('needs-you');
    expect(tokenSignal('ERR')).toBe('failed');
    expect(tokenSignal('QUE')).toBe('neutral');
    expect(tokenSignal('DON')).toBe('neutral');
    expect(tokenSignal('CAN')).toBe('neutral');
    expect(tokenSignal('SKP')).toBe('neutral');
  });
});

describe('hasLeftRule', () => {
  it('is true only for BLK and ERR — the binding rule leaves CHK out', () => {
    expect(hasLeftRule('BLK')).toBe(true);
    expect(hasLeftRule('ERR')).toBe(true);
    expect(hasLeftRule('CHK')).toBe(false);
    expect(hasLeftRule('CAN')).toBe(false);
  });
});

describe('progressText', () => {
  it('renders the full epics/stories/links line for an initiative Run', () => {
    expect(
      progressText(
        { epics_done: 1, epics_total: 2, stories_done: 5, stories_total: 8, links: 1 },
        null,
      ),
    ).toBe('1/2 epics · 5/8 stories · 1 link');
  });

  it('pluralises links', () => {
    expect(
      progressText(
        { epics_done: 0, epics_total: 1, stories_done: 0, stories_total: 3, links: 2 },
        null,
      ),
    ).toContain('2 links');
  });

  it('omits the epics clause when epics_total is null (an epic Run)', () => {
    expect(
      progressText(
        { epics_done: null, epics_total: null, stories_done: 2, stories_total: 4, links: 0 },
        null,
      ),
    ).toBe('2/4 stories · 0 links');
  });

  it('falls back to kindLabel when progress itself is null (repo-init)', () => {
    expect(progressText(null, 'repo-init')).toBe('repo-init');
  });
});

describe('oldestWaitSeconds', () => {
  it('is null with no queued or needs_you cards', () => {
    expect(oldestWaitSeconds([card({ status: 'running' }), card({ status: 'done' })])).toBeNull();
  });

  it('is the oldest age among queued and needs_you cards only', () => {
    const cards = [
      card({ status: 'running', age_seconds: 999_999 }),
      card({ status: 'queued', age_seconds: 100 }),
      card({ status: 'needs_you', age_seconds: 500 }),
    ];
    expect(oldestWaitSeconds(cards)).toBe(500);
  });
});

describe('footerReadoutText', () => {
  it('matches FooterReadout.astro byte-for-byte', () => {
    expect(footerReadoutText({ running: 2, queued: 1, needsYou: 3 }, '14:05:02')).toBe(
      '2 running · 1 queued / 3 need you / updated 14:05:02',
    );
  });
});

describe('surfaceReadoutText', () => {
  it('renders the bar readout with a real oldest wait', () => {
    expect(surfaceReadoutText(7, 2, 2 * 86400 + 4 * 3600)).toBe(
      '7 runs · 2 need you · oldest wait 2d 04h',
    );
  });

  it('singularises "run" at one', () => {
    expect(surfaceReadoutText(1, 0, null)).toBe('1 run · 0 need you · oldest wait —');
  });
});

describe('clockText', () => {
  it('renders hh:mm:ss', () => {
    expect(clockText('2026-01-01T09:05:02')).toBe('09:05:02');
  });
});

describe('capColumn', () => {
  it('shows every card under the cap, newest first, with nothing left out', () => {
    const cards = [
      card({ age_seconds: 200 }),
      card({ age_seconds: 50 }),
      card({ age_seconds: 100 }),
    ];
    const { shown, more } = capColumn(cards, 20);
    expect(shown.map((c) => c.age_seconds)).toEqual([50, 100, 200]);
    expect(more).toBe(0);
  });

  it('caps at the given size and reports how many were left out', () => {
    const cards = Array.from({ length: 25 }, (_, index) => card({ age_seconds: index }));
    const { shown, more } = capColumn(cards, 20);
    expect(shown).toHaveLength(20);
    expect(shown.map((c) => c.age_seconds)).toEqual(Array.from({ length: 20 }, (_, i) => i));
    expect(more).toBe(5);
  });
});

describe('moreNotShownText', () => {
  it('is empty when nothing was left out', () => {
    expect(moreNotShownText(0)).toBe('');
  });

  it('states the count otherwise', () => {
    expect(moreNotShownText(5)).toBe('5 more not shown');
  });
});

describe('boardRequestPath', () => {
  it('carries no project_id when unfiltered', () => {
    expect(boardRequestPath(null)).toBe('/api/runs?view=board');
  });

  it('carries project_id when filtered', () => {
    expect(boardRequestPath('proj-1')).toBe('/api/runs?view=board&project_id=proj-1');
  });
});

describe('fetchFailureMessage', () => {
  it('renders the status when one was received', () => {
    expect(fetchFailureMessage('GET', '/api/runs?view=board', 500)).toBe(
      'GET /api/runs?view=board → 500',
    );
  });

  it('renders "network error" when there was no response at all', () => {
    expect(fetchFailureMessage('GET', '/api/runs?view=board', null)).toBe(
      'GET /api/runs?view=board → network error',
    );
  });
});

describe('totalCards', () => {
  it('sums every column', () => {
    const board: BoardOut = {
      columns: {
        queued: [card()],
        running: [card(), card()],
        needs_you: [],
        done: [card()],
        failed: [],
      },
      counts: { queued: 1, running: 2, needs_you: 0 },
      generated_at: '2026-01-01T00:00:00Z',
    };
    expect(totalCards(board)).toBe(4);
  });
});
