import { expect, test } from '@playwright/test';

import { SESSION_COOKIE, SESSION_MAX_AGE_SECONDS, sign } from '../../src/lib/session';

import { ORCHESTRATOR_TOKEN, PREVIEW_URL, PROBE_SESSION_SECRET } from './config';
import { NO_SESSION, authenticatedStorageState } from './session';

/**
 * The guard, end to end (AD-4, FR-1). Every other spec runs logged in, because that is the
 * state the product is used in; this is the one file whose subject is the state before
 * that, so it is the one file that opts out of the session.
 *
 * The form is submitted through a real browser rather than through `request.post`: Astro
 * refuses a form-encoded POST that carries no `Origin` header, and a spec that worked
 * around that would not be exercising what a browser does.
 */
test.use({ storageState: NO_SESSION });

const GUARDED_PAGES = ['/', '/runs', '/projects', '/templates', '/workflows/new'];

const AMBER = 'rgb(228, 179, 60)';
const RED = 'rgb(224, 82, 82)';

test.describe('with no session', () => {
  for (const path of GUARDED_PAGES) {
    test(`${path} is redirected to the login screen`, async ({ request }) => {
      const response = await request.get(path, { maxRedirects: 0 });

      expect(response.status()).toBe(302);
      expect(response.headers()['location']).toBe('/login');
    });
  }

  test('the proxy refuses rather than redirecting, and reaches no upstream', async ({
    request,
  }) => {
    const response = await request.get('/api/ping', { maxRedirects: 0 });

    expect(response.status()).toBe(401);
    expect(response.headers()['content-type']).toContain('application/problem+json');
    expect(await response.json()).toMatchObject({ title: 'unauthorized', status: 401 });
    // the stub backend answers `{"pong": true}` to an authorised call; it was never asked
    expect(await response.text()).not.toContain('pong');
  });

  test('the login screen is served, and states the mechanism', async ({ page }) => {
    const response = await page.goto('/login');

    expect(response?.status()).toBe(200);
    await expect(page.getByTestId('login-hint')).toHaveText(
      'the token is ORCHESTRATOR_TOKEN in the instance .env · session cookie lasts 30 days',
    );
    await expect(page.getByTestId('login-token')).toHaveAttribute('type', 'password');
    await expect(page.getByTestId('login-token')).toHaveAttribute('autocomplete', 'off');
    await expect(page.locator('label[for="login-token"]')).toHaveText('ACCESS TOKEN');
    await expect(page.getByTestId('login-submit')).toHaveText('ENTER');
    await expect(page.getByTestId('login-rejected')).toHaveCount(0);
  });

  test('the login screen carries no credential and paints no signal colour', async ({
    page,
    request,
  }) => {
    const served = await request.get('/login', { maxRedirects: 0 });
    expect(await served.text()).not.toContain(ORCHESTRATOR_TOKEN);
    for (const value of Object.values(served.headers())) {
      expect(value).not.toContain(ORCHESTRATOR_TOKEN);
    }

    await page.goto('/login');
    const painted = await page.evaluate(() =>
      [...document.querySelectorAll('*')].flatMap((element) => {
        const style = getComputedStyle(element);
        return [style.color, style.backgroundColor, style.borderTopColor];
      }),
    );

    expect(painted.length).toBeGreaterThan(10);
    expect(painted.filter((value) => value === AMBER || value === RED)).toEqual([]);
  });
});

test.describe('submitting the form', () => {
  test('a wrong token re-renders the screen with no cookie and no redirect', async ({ page }) => {
    await page.goto('/login');
    await page.getByTestId('login-token').fill('not-the-instance-token');

    const [response] = await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'POST'),
      page.getByTestId('login-submit').click(),
    ]);

    expect(response.status()).toBe(200);
    expect(await response.headerValue('set-cookie')).toBeNull();
    await expect(page.getByTestId('login-rejected')).toHaveText('token rejected');
    await expect(page.getByTestId('login-rejected')).toHaveCSS('color', RED);
    await expect(page.getByTestId('login-hint')).toHaveCount(0);
    await expect(page.getByTestId('login-token')).toHaveValue('');
    expect(new URL(page.url()).pathname).toBe('/login');
    expect(await page.context().cookies()).toEqual([]);
  });

  test('an empty token is answered exactly as a wrong one', async ({ page }) => {
    await page.goto('/login');

    const [response] = await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'POST'),
      page.getByTestId('login-submit').click(),
    ]);

    // the same status, the same line, the same absence of a cookie: a screen that told the
    // two cases apart would be telling a guesser which half of the guess was right
    expect(response.status()).toBe(200);
    expect(await response.headerValue('set-cookie')).toBeNull();
    await expect(page.getByTestId('login-rejected')).toHaveText('token rejected');
    expect(await page.context().cookies()).toEqual([]);
  });

  test('the right token sets the 30-day session and opens the Board', async ({ page }) => {
    await page.goto('/login');
    await page.getByTestId('login-token').fill(ORCHESTRATOR_TOKEN);

    const [response] = await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'POST'),
      page.getByTestId('login-submit').click(),
    ]);

    expect(response.status()).toBe(302);
    expect(await response.headerValue('location')).toBe('/');

    const setCookie = (await response.headerValue('set-cookie')) ?? '';
    expect(setCookie).toContain(`${SESSION_COOKIE}=`);
    expect(setCookie).toContain('Max-Age=2592000');
    expect(setCookie).toContain('Path=/');
    expect(setCookie).toContain('HttpOnly');
    expect(setCookie).toContain('SameSite=Lax');
    // the preview server speaks http, and a `Secure` cookie would be discarded on arrival
    expect(setCookie).not.toContain('Secure');
    // the session is a signed timestamp; the credential stays on the server (AD-4)
    expect(setCookie).not.toContain(ORCHESTRATOR_TOKEN);
    expect(SESSION_MAX_AGE_SECONDS).toBe(2_592_000);

    await page.waitForURL(`${PREVIEW_URL}/`);
    await expect(page.getByTestId('board-empty')).toContainText('NOTHING REGISTERED');
    // the readout names the one surface that changes what it says
    const register = page.getByTestId('board-empty').getByRole('link', {
      name: 'register a project to start',
    });
    await expect(register).toHaveAttribute('href', '/projects');

    const [cookie] = await page.context().cookies();
    expect(cookie?.name).toBe(SESSION_COOKIE);
    expect(cookie?.httpOnly).toBe(true);
  });
});

test.describe('a cookie that is not a session', () => {
  const cookie = (value: string) => ({
    name: SESSION_COOKIE,
    value,
    domain: new URL(PREVIEW_URL).hostname,
    path: '/',
  });

  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test('an altered signature is treated as absent', async ({ page }) => {
    const valid = sign(Date.now(), PROBE_SESSION_SECRET);
    await page
      .context()
      .addCookies([cookie(`${valid.slice(0, -1)}${valid.endsWith('a') ? 'b' : 'a'}`)]);

    await page.goto('/');

    expect(new URL(page.url()).pathname).toBe('/login');
  });

  test('an issued-at older than 30 days is treated as absent', async ({ page }) => {
    const expired = Date.now() - (SESSION_MAX_AGE_SECONDS * 1000 + 60_000);
    await page.context().addCookies([cookie(sign(expired, PROBE_SESSION_SECRET))]);

    await page.goto('/');

    expect(new URL(page.url()).pathname).toBe('/login');
  });
});

test.describe('with a session', () => {
  test('the proxy forwards with the bearer and answers the backend', async ({ browser }) => {
    const context = await browser.newContext({
      baseURL: PREVIEW_URL,
      storageState: authenticatedStorageState(),
    });

    const response = await context.request.get('/api/ping');

    expect(response.status()).toBe(200);
    expect(await response.json()).toEqual({ pong: true });
    await context.close();
  });
});
