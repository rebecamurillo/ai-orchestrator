/**
 * The session every spec runs with, unless it says otherwise.
 *
 * Story 1.5 put a guard in front of every page and in front of the proxy, which is exactly
 * what `smoke.spec.ts`, `shell.spec.ts` and `no-credential.spec.ts` — written before it —
 * drive with no session at all. Those three files are frozen, so the session is supplied
 * from outside them: `playwright.config.ts` sets this as `use.storageState`, and Playwright
 * applies it to the `page` fixture and to the `request` fixture alike. Being logged in is
 * the default state of the product for everything except the login screen, so it is the
 * right default for the harness too.
 *
 * The cookie is minted by `src/lib/session.ts` — the same module the middleware verifies
 * with — rather than by a copy of its format here. A change to the cookie that the server
 * would reject cannot pass this harness.
 *
 * `PROBE_SESSION_SECRET` is what `playwright.config.ts` gives the preview server as
 * `ORCHESTRATOR_SESSION_SECRET`, in both stub and `E2E_BACKEND=real` mode. It is a visible
 * placeholder, not a credential: it signs a timestamp and nothing else.
 */
import { SESSION_COOKIE, SESSION_MAX_AGE_SECONDS, sign } from '../../src/lib/session';

import { PREVIEW_URL, PROBE_SESSION_SECRET } from './config';

type StorageState = { cookies: Cookie[]; origins: [] };

type Cookie = {
  name: string;
  value: string;
  domain: string;
  path: string;
  expires: number;
  httpOnly: boolean;
  secure: boolean;
  sameSite: 'Lax';
};

/** A storage state holding one freshly issued `orch_session` for the preview server. */
export function authenticatedStorageState(): StorageState {
  const issuedAt = Date.now();
  return {
    cookies: [
      {
        name: SESSION_COOKIE,
        value: sign(issuedAt, PROBE_SESSION_SECRET),
        // an IP host matches on the literal address; `localhost` would not be sent here
        domain: new URL(PREVIEW_URL).hostname,
        path: '/',
        expires: Math.floor(issuedAt / 1000) + SESSION_MAX_AGE_SECONDS,
        httpOnly: true,
        secure: false,
        sameSite: 'Lax',
      },
    ],
    origins: [],
  };
}

/** What a spec opts into when the thing it is measuring is the guard itself. */
export const NO_SESSION: StorageState = { cookies: [], origins: [] };
