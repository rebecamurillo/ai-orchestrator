/**
 * The one place `ORCHESTRATOR_TOKEN` is compared (AD-4). The other place it is read at all
 * is `src/api/server.ts`, which attaches it to a backend-api request; nothing else in
 * web-client touches it, and nothing the browser downloads can import either module.
 *
 * On a match the Operator gets a signed timestamp, not the token: `src/lib/session.ts`
 * mints the cookie, and the credential stays on the server. On a mismatch the Action throws
 * an `ActionError`, which the login page renders in place — Astro's form Actions post back
 * to the page itself, so there is no redirect and no flash of a lost form (spine
 * conventions, "Form errors").
 *
 * A per-IP in-memory lockout guards against token guessing (AD-4): five wrong tokens
 * within 15 minutes lock the IP for the same 15-minute window. `src/lib/lockout.ts` owns
 * the counter; this handler calls `clear(ip)` on a successful login so the next attempt
 * starts from zero.
 */
import { ActionError, defineAction } from 'astro:actions';
import { ORCHESTRATOR_SESSION_SECRET, ORCHESTRATOR_TOKEN } from 'astro:env/server';

import { clear, locked_until, record_failure, remaining } from '../lib/lockout';
import { SESSION_COOKIE, sessionCookieOptions, sign, tokenMatches } from '../lib/session';

export const login = defineAction({
  accept: 'form',
  handler: (form: FormData, context) => {
    const ip = context.clientAddress ?? '0.0.0.0';
    const now = Date.now();

    // Lockout check runs before token inspection; a locked IP never reaches the comparison.
    const lu = locked_until(ip, now);
    if (lu !== null) {
      const m = Math.ceil((lu - now) / 60_000);
      throw new ActionError({
        code: 'FORBIDDEN',
        message: `too many attempts — try again in ${m} min`,
      });
    }

    const submitted = form.get('token');
    // one answer for a wrong token, an empty field and a field that was not sent at all:
    // a login screen that says which of the three happened is a login screen that helps
    if (typeof submitted !== 'string' || !tokenMatches(submitted, ORCHESTRATOR_TOKEN)) {
      record_failure(ip, now);
      const r = remaining(ip, now);
      if (r === 0) {
        // fifth failure just pushed the IP into lockout
        const lu2 = locked_until(ip, now)!;
        const m = Math.ceil((lu2 - now) / 60_000);
        throw new ActionError({
          code: 'FORBIDDEN',
          message: `too many attempts — try again in ${m} min`,
        });
      }
      throw new ActionError({
        code: 'UNAUTHORIZED',
        message: `token rejected — ${r} attempts left`,
      });
    }

    // Success: clear the failure counter before writing the session cookie.
    clear(ip);
    context.cookies.set(
      SESSION_COOKIE,
      sign(Date.now(), ORCHESTRATOR_SESSION_SECRET),
      // the attributes are fixed in `src/lib/session.ts`, where they are unit-tested; the
      // only thing decided here is whether this request could honour a `Secure` cookie
      sessionCookieOptions(context.url.protocol === 'https:'),
    );

    return { ok: true };
  },
});
