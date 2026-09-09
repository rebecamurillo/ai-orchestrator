/**
 * `lib/run/accept.ts` (6.6, FR-31, AD-17) — reading the hit list off the wire, marking each
 * file, linking its diff, the accept line, and the body the button posts.
 *
 * `alert.payload` is `Record<string, unknown>` on the wire, because `GateRecord.payload` is
 * deliberately open ("whatever the event needs kept"). So most of this file is about a shape
 * that is not the one written today: a Run parked by an older backend, or by a call site that
 * records paths without kinds, must render as much as it can rather than throw on a screen
 * that polls.
 */
import { describe, expect, it } from 'vitest';

import {
  ACCEPT_LABEL,
  acceptBody,
  acceptLine,
  diffHref,
  hitMark,
  offersAccept,
  protectedHits,
} from '../../src/lib/run/accept';
import type { AlertOut, RunDetailOut, SignalKind } from '../../src/lib/run/detail';

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939c2';

function alert(payload: unknown): AlertOut {
  return {
    token: 'BLK',
    reason: 'protected path modified: tests/a.py, AGENTS.md',
    park_kind: 'protected_path',
    payload,
  } as unknown as AlertOut;
}

const HITS = {
  hits: [
    { path: 'tests/a.py', kind: 'modified' },
    { path: 'AGENTS.md', kind: 'added' },
  ],
};

describe('protectedHits', () => {
  it('reads each file and its kind, in the order AD-17 reported them', () => {
    expect(protectedHits(alert(HITS))).toEqual([
      { path: 'tests/a.py', kind: 'modified' },
      { path: 'AGENTS.md', kind: 'added' },
    ]);
  });

  it('reads a hit that carries no kind, which is what the commit guard records', () => {
    expect(protectedHits(alert({ hits: [{ path: 'AGENTS.md' }] }))).toEqual([
      { path: 'AGENTS.md', kind: '' },
    ]);
  });

  it.each([
    ['no alert at all', null],
    ['an alert with no payload', undefined],
  ])('answers nothing for %s', (_name, given) => {
    expect(protectedHits(given as AlertOut | null | undefined)).toEqual([]);
  });

  it.each([
    ['a payload with no hits', {}],
    ['hits that are not a list', { hits: 'AGENTS.md' }],
    ['hits that are null', { hits: null }],
  ])('answers nothing for %s', (_name, payload) => {
    expect(protectedHits(alert(payload))).toEqual([]);
  });

  it('skips an entry that is not a mapping with a string path, and keeps the rest', () => {
    const payload = {
      hits: ['AGENTS.md', null, 7, { kind: 'added' }, { path: 3 }, { path: 'a.py' }],
    };

    expect(protectedHits(alert(payload))).toEqual([{ path: 'a.py', kind: '' }]);
  });
});

describe('hitMark', () => {
  it('marks an added file, a deleted one, and a modified one', () => {
    expect([hitMark('added'), hitMark('deleted'), hitMark('modified')]).toEqual(['+', '−', '~']);
  });

  it('marks a hit whose park recorded no kind the same as a modification', () => {
    expect(hitMark('')).toBe('~');
  });
});

describe('diffHref', () => {
  it('points at the diff mode of the files endpoint', () => {
    expect(diffHref(RUN_ID, 'AGENTS.md')).toBe(`/api/runs/${RUN_ID}/files?path=AGENTS.md&diff=1`);
  });

  it('encodes a path with slashes and spaces so the query stays one parameter', () => {
    expect(diffHref(RUN_ID, 'tests/a b.py')).toContain('path=tests%2Fa%20b.py');
  });
});

describe('acceptLine', () => {
  it('names every consequence, verbatim', () => {
    expect(acceptLine('4-1')).toBe(
      'Accept records these files as accepted for story 4-1; ' +
        'the check resumes on the same tree and the files ship with the story',
    );
  });

  it('says "this story" rather than inventing an id the response did not carry', () => {
    expect(acceptLine('')).toContain('accepted for this story;');
  });
});

describe('acceptBody', () => {
  it('posts the paths under continue, which is the signal AD-13 names', () => {
    expect(acceptBody(['tests/a.py', 'AGENTS.md'])).toEqual({
      kind: 'continue',
      payload: { files: ['tests/a.py', 'AGENTS.md'] },
    });
  });
});

describe('offersAccept', () => {
  function detail(over: Partial<RunDetailOut>): RunDetailOut {
    return {
      alert: alert(HITS),
      admitted_signals: ['continue', 'retry', 'cancel'] as SignalKind[],
      ...over,
    } as unknown as RunDetailOut;
  }

  it('is offered on a protected-path stop that admits continue and recorded files', () => {
    expect(offersAccept(detail({}), 'protected_path')).toBe(true);
  });

  it('is not offered on another stop, even one that admits continue', () => {
    expect(offersAccept(detail({}), 'checkpoint')).toBe(false);
    expect(offersAccept(detail({}), null)).toBe(false);
  });

  it('is not offered when the server does not admit continue', () => {
    const without = detail({ admitted_signals: ['retry', 'cancel'] as SignalKind[] });

    expect(offersAccept(without, 'protected_path')).toBe(false);
  });

  it('is not offered when the park recorded no files, since there is nothing to accept', () => {
    const empty = detail({ alert: alert({ hits: [] }) });

    expect(offersAccept(empty, 'protected_path')).toBe(false);
  });
});

describe('the button', () => {
  it("reads the brief's own words", () => {
    expect(ACCEPT_LABEL).toBe('Accept changes');
  });
});
