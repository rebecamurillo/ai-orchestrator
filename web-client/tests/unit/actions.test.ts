/**
 * The login Action, exercised without a browser.
 *
 * `tests/e2e/login.spec.ts` proves the screen; what it cannot show is which of the two
 * branches ran, because a rejected login and a login that never set a cookie look the same
 * from the outside. The Action is driven here with a recording cookie jar, so "the
 * credential is compared and never re-emitted" (AD-4) is asserted against the value that is
 * actually written.
 *
 * Astro hands an Action its `ActionAPIContext` as `this` and refuses a call whose context
 * is not marked, so the double below carries the marker Astro looks for —
 * `Symbol.for('astro.actionAPIContext')`, a global-registry symbol that needs no import from
 * inside the framework. `orThrow` is the server-side entry point that raises the
 * `ActionError` instead of wrapping it in a result.
 */
import { describe, expect, it } from 'vitest';

import { server } from '../../src/actions/index';
import { login } from '../../src/actions/login';
import { SESSION_COOKIE, verify } from '../../src/lib/session';
import { ORCHESTRATOR_SESSION_SECRET, ORCHESTRATOR_TOKEN } from '../stubs/astro-env-server';

const ACTION_CONTEXT = Symbol.for('astro.actionAPIContext');

type Written = { name: string; value: string; options: Record<string, unknown> };

function context(protocol: 'http:' | 'https:' = 'https:') {
  const written: Written[] = [];
  return {
    [ACTION_CONTEXT]: true,
    written,
    cookies: {
      set: (name: string, value: string, options: Record<string, unknown>) =>
        written.push({ name, value, options }),
    },
    url: new URL(`${protocol}//127.0.0.1:4321/login`),
  };
}

function form(token?: string): FormData {
  const body = new FormData();
  if (token !== undefined) body.set('token', token);
  return body;
}

function submit(body: FormData, ctx: ReturnType<typeof context>): Promise<unknown> {
  return login.orThrow.call(ctx, body);
}

describe('the registry Astro builds `astro:actions` from', () => {
  it('exports the login Action under the name the form posts to', () => {
    expect(server.login).toBe(login);
  });
});

describe('the login Action', () => {
  it('mints a session cookie the session module verifies', async () => {
    const ctx = context();

    await expect(submit(form(ORCHESTRATOR_TOKEN), ctx)).resolves.toEqual({ ok: true });

    const [cookie] = ctx.written;
    expect(cookie!.name).toBe(SESSION_COOKIE);
    expect(verify(cookie!.value, ORCHESTRATOR_SESSION_SECRET, Date.now())).toBe(true);
  });

  it('writes a signed timestamp, never the credential itself', async () => {
    const ctx = context();

    await submit(form(ORCHESTRATOR_TOKEN), ctx);

    expect(ctx.written[0]!.value).not.toContain(ORCHESTRATOR_TOKEN);
  });

  it('drops Secure on a plain-http request and keeps it on https', async () => {
    const secure = context('https:');
    const plain = context('http:');

    await submit(form(ORCHESTRATOR_TOKEN), secure);
    await submit(form(ORCHESTRATOR_TOKEN), plain);

    expect(secure.written[0]!.options.secure).toBe(true);
    expect(plain.written[0]!.options.secure).toBe(false);
  });

  it.each([
    ['a wrong token', 'not-the-token'],
    ['an empty field', ''],
    ['a token one character short', ORCHESTRATOR_TOKEN.slice(0, -1)],
  ])('answers %s with `token rejected` and sets no cookie', async (_case, submitted) => {
    const ctx = context();

    await expect(submit(form(submitted), ctx)).rejects.toThrow('token rejected');
    expect(ctx.written).toEqual([]);
  });

  it('answers a field that was not sent at all the same way', async () => {
    const ctx = context();

    await expect(submit(form(), ctx)).rejects.toThrow('token rejected');
    expect(ctx.written).toEqual([]);
  });
});
