/**
 * The session cookie is the whole of the guard (AD-4), so it is tested as a value rather
 * than through a page: `sign` mints it, `verify` decides, and `tokenMatches` is the one
 * place the instance credential is compared.
 *
 * The secret below is a fixed placeholder, never a credential — the point of these cases
 * is that a cookie signed with one secret is refused by another, which needs two visible
 * strings and no real value.
 */
import { createHmac } from 'node:crypto';

import { describe, expect, it } from 'vitest';

import {
  SESSION_COOKIE,
  SESSION_MAX_AGE_SECONDS,
  sessionCookieOptions,
  sign,
  tokenMatches,
  verify,
} from '../../src/lib/session';

const SECRET = 'fixed-session-secret-for-the-unit-run';
const OTHER_SECRET = 'a-different-session-secret';
const ISSUED_AT = Date.UTC(2026, 8, 4, 6, 0, 0);
const MAX_AGE_MS = SESSION_MAX_AGE_SECONDS * 1000;

describe('the cookie name and lifetime', () => {
  it('are the two figures the architecture fixes', () => {
    expect(SESSION_COOKIE).toBe('orch_session');
    // 30 days, the number that goes on the wire as Max-Age
    expect(SESSION_MAX_AGE_SECONDS).toBe(2_592_000);
  });
});

describe('sign', () => {
  it('is the issued-at and its HMAC, and nothing else', () => {
    const value = sign(ISSUED_AT, SECRET);

    expect(value).toBe(
      `${ISSUED_AT}.${createHmac('sha256', SECRET).update(String(ISSUED_AT)).digest('hex')}`,
    );
    expect(value).toMatch(/^\d+\.[0-9a-f]{64}$/);
  });

  it('carries no part of the secret it was signed with', () => {
    // the cookie reaches the browser; the credential and the signing key never do (AD-4)
    expect(sign(ISSUED_AT, SECRET)).not.toContain(SECRET);
  });

  it('changes when the secret changes', () => {
    expect(sign(ISSUED_AT, SECRET)).not.toBe(sign(ISSUED_AT, OTHER_SECRET));
  });
});

describe('verify', () => {
  it('accepts a cookie it just signed', () => {
    expect(verify(sign(ISSUED_AT, SECRET), SECRET, ISSUED_AT)).toBe(true);
  });

  it('refuses one signed with another secret', () => {
    expect(verify(sign(ISSUED_AT, OTHER_SECRET), SECRET, ISSUED_AT)).toBe(false);
  });

  it('refuses a signature with one character changed', () => {
    const value = sign(ISSUED_AT, SECRET);
    const flipped = value.slice(0, -1) + (value.endsWith('a') ? 'b' : 'a');

    expect(flipped).not.toBe(value);
    expect(verify(flipped, SECRET, ISSUED_AT)).toBe(false);
  });

  it('refuses an issued-at rewritten under a signature that was valid', () => {
    const [, signature] = sign(ISSUED_AT, SECRET).split('.');

    expect(verify(`${ISSUED_AT + 1}.${signature}`, SECRET, ISSUED_AT + 1)).toBe(false);
  });

  it.each([
    ['undefined', undefined],
    ['empty', ''],
    ['no separator', '123456789'],
    ['no signature', '123456789.'],
    ['no issued-at', `.${'0'.repeat(64)}`],
    ['a non-numeric issued-at', `not-a-number.${'0'.repeat(64)}`],
    ['a negative issued-at', `-1.${'0'.repeat(64)}`],
    ['a signature of the wrong length', '123456789.abc'],
    ['a signature that is not hex', `123456789.${'z'.repeat(64)}`],
    ['two separators', `${ISSUED_AT}.${'0'.repeat(64)}.extra`],
  ])('refuses %s rather than throwing', (_case, value) => {
    expect(verify(value, SECRET, ISSUED_AT)).toBe(false);
  });

  it('accepts the cookie on its last millisecond and refuses it on the next', () => {
    const value = sign(ISSUED_AT, SECRET);

    expect(verify(value, SECRET, ISSUED_AT + MAX_AGE_MS)).toBe(true);
    expect(verify(value, SECRET, ISSUED_AT + MAX_AGE_MS + 1)).toBe(false);
  });

  it('refuses a cookie issued in the future', () => {
    // the server signs with its own clock, so a future issued-at is not a cookie it wrote
    expect(verify(sign(ISSUED_AT, SECRET), SECRET, ISSUED_AT - 1)).toBe(false);
  });
});

describe('tokenMatches', () => {
  it('accepts the same token', () => {
    expect(tokenMatches('the-instance-token', 'the-instance-token')).toBe(true);
  });

  it('refuses a different token of the same length', () => {
    expect(tokenMatches('the-instance-tokeX', 'the-instance-token')).toBe(false);
  });

  it.each([
    ['a longer submission', 'the-instance-token-and-more'],
    ['a shorter submission', 'the-instance'],
    ['an empty submission', ''],
  ])('refuses %s without throwing on the length difference', (_case, submitted) => {
    // `timingSafeEqual` is a TypeError on unequal buffers, so the comparison is made over
    // digests: equal length by construction, and no length is leaked by the answer
    expect(tokenMatches(submitted, 'the-instance-token')).toBe(false);
  });

  it('refuses everything when the instance has no token configured', () => {
    // an unset credential must not turn into "any empty submission is correct"
    expect(tokenMatches('', '')).toBe(false);
    expect(tokenMatches('anything', '')).toBe(false);
  });
});

describe('sessionCookieOptions', () => {
  it('fixes every attribute but Secure', () => {
    expect(sessionCookieOptions(false)).toEqual({
      httpOnly: true,
      sameSite: 'lax',
      path: '/',
      maxAge: 2_592_000,
      secure: false,
    });
  });

  it('marks the cookie Secure only where the request could honour it', () => {
    // a `Secure` cookie sent over plain http is discarded by the browser, which presents as
    // a login that succeeds and then bounces straight back to the screen
    expect(sessionCookieOptions(true).secure).toBe(true);
    expect(sessionCookieOptions(false).secure).toBe(false);
  });
});

describe('a misconfigured instance', () => {
  it('refuses every session rather than accepting every forgery', () => {
    // `createHmac` accepts an empty key, so without this an instance whose signing secret
    // was left blank would verify a cookie anyone could compute
    expect(verify(sign(ISSUED_AT, ''), '', ISSUED_AT)).toBe(false);
    expect(verify(sign(ISSUED_AT, SECRET), '', ISSUED_AT)).toBe(false);
  });
});

describe('the cookie has one spelling per session', () => {
  it.each([
    ['leading zeros', `0${ISSUED_AT}`],
    ['a plus sign', `+${ISSUED_AT}`],
  ])('refuses %s in the issued-at', (_case, issuedAt) => {
    // the HMAC is computed over `String(issuedAt)`, so a second spelling that parses to the
    // same number would be a second valid cookie for one session
    const [, signature] = sign(ISSUED_AT, SECRET).split('.');

    expect(verify(`${issuedAt}.${signature}`, SECRET, ISSUED_AT)).toBe(false);
  });
});
