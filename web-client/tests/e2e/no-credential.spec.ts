import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

import { PROBE_TOKEN, USE_REAL_BACKEND } from './config';

/**
 * AD-1 end to end: the proxy adds the credential on the server side and nothing carries it
 * back. The unit tests assert this against a mocked upstream; here it is a real build, a
 * real Node server and a real HTTP round trip.
 */

const DIST = new URL('../../dist', import.meta.url).pathname;

function filesUnder(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    return statSync(path).isDirectory() ? filesUnder(path) : [path];
  });
}

test('the build carries no credential at all', () => {
  const files = filesUnder(DIST);

  expect(files.length).toBeGreaterThan(0);
  for (const file of files) {
    // `latin1`, not `utf8`: a future font or image in the build must be searched, not
    // decoded, and a decode failure would silently turn this assertion into nothing
    expect(readFileSync(file).toString('latin1'), file).not.toContain(PROBE_TOKEN);
  }
});

test('nothing the browser downloads mentions the server credential', () => {
  const clientFiles = filesUnder(join(DIST, 'client'));

  expect(clientFiles.length).toBeGreaterThan(0);
  for (const file of clientFiles) {
    const source = readFileSync(file).toString('latin1');
    expect(source, file).not.toContain('ORCHESTRATOR_TOKEN');
    expect(source, file).not.toContain('astro:env/server');
    expect(source, file).not.toContain('BACKEND_API_URL');
  }
});

test('the served page carries no credential', async ({ request }) => {
  const response = await request.get('/');

  expect(response.status()).toBe(200);
  expect(await response.text()).not.toContain(PROBE_TOKEN);
  for (const value of Object.values(response.headers())) {
    expect(value).not.toContain(PROBE_TOKEN);
  }
});

test('the proxy adds the bearer the browser never had', async ({ request }) => {
  const response = await request.get('/api/ping');

  expect(response.status()).toBe(200);
  expect(await response.json()).toEqual({ pong: true });
  expect(response.headers()['cache-control']).toBe('no-store');
});

test('an upstream that echoes the credential does not reach the browser', async ({ request }) => {
  test.skip(USE_REAL_BACKEND, 'the echo route exists only in the stub backend');

  const response = await request.get('/api/echo-auth');

  expect(response.status()).toBe(200);
  for (const [name, value] of Object.entries(response.headers())) {
    expect(value, name).not.toContain(PROBE_TOKEN);
  }
});
