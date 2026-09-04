/**
 * The Operator's session, as a value rather than a store (AD-4).
 *
 * The cookie is `<issued-at ms>.<hmac-sha256(issued-at, secret)>`. Nothing is persisted, so
 * there is no session table to migrate and nothing to lose across a restart — and, more to
 * the point, the cookie carries no part of `ORCHESTRATOR_TOKEN`. The credential is compared
 * once, at login; from then on the browser holds only a signed timestamp.
 *
 * Every function here is pure and takes its secret as an argument. That is load-bearing
 * twice: it makes the module unit-testable with a fixed placeholder, and it lets
 * `playwright.config.ts` import it, so the e2e harness mints its session with exactly the
 * code the server verifies rather than a hand-rolled copy that can drift.
 */
import { createHash, createHmac, timingSafeEqual } from 'node:crypto';

/** The one cookie this product sets. */
export const SESSION_COOKIE = 'orch_session';

/** 30 days, in the unit `Max-Age` is written in. */
export const SESSION_MAX_AGE_SECONDS = 2_592_000;

/**
 * `<digits>.<64 hex>` and nothing else; anything shaped differently is not ours.
 *
 * The issued-at is matched in its canonical spelling — no leading zeros — because the HMAC
 * is computed over `String(issuedAt)`. `007.<hmac of 7>` would otherwise be a second, equally
 * valid spelling of the same session, and one cookie value per session is easier to reason
 * about than a family of them.
 */
const COOKIE_SHAPE = /^(0|[1-9]\d*)\.([0-9a-f]{64})$/;

/** Cookie attributes, as `Astro.cookies.set` takes them (AD-4). */
export type SessionCookieOptions = {
  httpOnly: true;
  sameSite: 'lax';
  path: '/';
  maxAge: number;
  secure: boolean;
};

/**
 * The attributes the session cookie is always written with.
 *
 * `secure` is the one that varies, and it is passed in rather than decided here: over plain
 * http a `Secure` cookie is discarded by the browser, which would present as a login that
 * succeeds and then does nothing at all. Everything else is fixed — `HttpOnly` so no script
 * can read the session, `SameSite=Lax` so it is not sent on a cross-site POST, `Path=/`
 * because the guard covers every route, and 30 days.
 */
export function sessionCookieOptions(secure: boolean): SessionCookieOptions {
  return { httpOnly: true, sameSite: 'lax', path: '/', maxAge: SESSION_MAX_AGE_SECONDS, secure };
}

/**
 * A sha256 digest of the input.
 *
 * Every constant-time comparison below runs over one of these rather than over the raw
 * strings: `timingSafeEqual` throws a TypeError on buffers of different length, and
 * checking the length first would answer "wrong length" faster than "wrong content".
 * Digesting makes both sides 32 bytes by construction and leaks neither.
 */
function digest(value: string): Buffer {
  return createHash('sha256').update(value, 'utf8').digest();
}

function signature(issuedAt: number, secret: string): string {
  return createHmac('sha256', secret).update(String(issuedAt)).digest('hex');
}

/** The cookie value for a session issued at `issuedAt` (epoch milliseconds). */
export function sign(issuedAt: number, secret: string): string {
  return `${issuedAt}.${signature(issuedAt, secret)}`;
}

/**
 * Whether `value` is a cookie this instance signed and is not yet 30 days old.
 *
 * Never throws and never distinguishes its reasons: a tampered signature, a rewritten
 * issued-at, a malformed value and an expired one are all "no session", which is what lets
 * the middleware treat an invalid cookie as an absent one.
 */
export function verify(value: string | undefined, secret: string, now: number): boolean {
  // an instance with no signing key configured must refuse every session rather than accept
  // every forgery: `createHmac` is perfectly happy with an empty key, so this is the check
  // that decides which way a misconfigured instance fails
  if (secret.length === 0) return false;

  const match = value === undefined ? null : COOKIE_SHAPE.exec(value);
  if (!match) return false;

  const issuedAt = Number(match[1]);
  if (!Number.isSafeInteger(issuedAt)) return false;

  const age = now - issuedAt;
  // a future issued-at is not a cookie this server wrote, so it is refused rather than
  // tolerated as clock skew
  if (age < 0 || age > SESSION_MAX_AGE_SECONDS * 1000) return false;

  return timingSafeEqual(digest(match[2]!), digest(signature(issuedAt, secret)));
}

/**
 * Whether the submitted token is the instance credential (AD-4).
 *
 * An instance with no token configured matches nothing, rather than matching an empty
 * submission — a missing credential must fail closed.
 */
export function tokenMatches(submitted: string, expected: string): boolean {
  if (expected.length === 0) return false;
  return timingSafeEqual(digest(submitted), digest(expected));
}
