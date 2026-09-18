/**
 * TDD tests for `lib/step-path.ts` — the bracket↔dot-index bijection (AD-15, story 1-2).
 *
 * Written first, before the implementation exists. All tests must fail until
 * `web-client/src/lib/step-path.ts` is created.
 */
import { describe, it, expect } from 'vitest';
import { encode, decode } from '../../src/lib/step-path';

describe('encode', () => {
  it('converts [n] occurrences to .n', () => {
    expect(encode('epics[0].stories[3].build')).toBe('epics.0.stories.3.build');
  });

  it('leaves a root-only path unchanged', () => {
    expect(encode('plan')).toBe('plan');
  });

  it('handles a single trailing bracket index', () => {
    expect(encode('steps[0]')).toBe('steps.0');
  });

  it('handles multiple bracket indices in sequence', () => {
    expect(encode('epics[1].stories[2].verify')).toBe('epics.1.stories.2.verify');
  });

  it('does not affect alphabetic dot-separated segments', () => {
    expect(encode('steps.build')).toBe('steps.build');
  });
});

describe('decode', () => {
  it('converts .n (pure-digit segment) to [n]', () => {
    expect(decode('epics.0.stories.3.build')).toBe('epics[0].stories[3].build');
  });

  it('leaves a root-only path unchanged', () => {
    expect(decode('plan')).toBe('plan');
  });

  it('does not convert non-digit segments', () => {
    expect(decode('epics.stories.build')).toBe('epics.stories.build');
  });

  it('handles a single trailing digit segment', () => {
    expect(decode('steps.0')).toBe('steps[0]');
  });
});

describe('round-trip', () => {
  it('decode(encode(b)) === b for representative bracket path', () => {
    const b = 'epics[0].stories[3].build';
    expect(decode(encode(b))).toBe(b);
  });

  it('encode(decode(d)) === d for representative dot-index path', () => {
    const d = 'epics.0.stories.3.build';
    expect(encode(decode(d))).toBe(d);
  });

  it('is lossless for a root-only path (no brackets)', () => {
    expect(decode(encode('plan'))).toBe('plan');
    expect(encode(decode('plan'))).toBe('plan');
  });

  it('is lossless for steps[0]', () => {
    expect(decode(encode('steps[0]'))).toBe('steps[0]');
  });

  it('is lossless for a deeply nested path', () => {
    const b = 'epics[0].stories[3].build';
    expect(decode(encode(b))).toBe(b);
  });
});
