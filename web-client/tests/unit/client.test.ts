/**
 * `src/api/client.ts` is the browser's only fetch caller (AD-1): bound to the same-origin
 * proxy under `/api`, never to backend-api, and carrying no credential of its own.
 *
 * It is asserted by construction rather than by calling it. openapi-fetch builds a
 * `Request` before it calls `fetch`, and a relative base URL has no document to resolve
 * against outside a browser — `new Request('/api/ping')` throws in Node. The client's
 * behaviour over the wire is covered where a browser exists: `tests/e2e/`.
 */
import { readFileSync } from 'node:fs';

import { expect, it } from 'vitest';

import { API_BASE_URL, api } from '../../src/api/client';

const SOURCE = readFileSync(new URL('../../src/api/client.ts', import.meta.url), 'utf8');

/** Prose may name what the module must not do; the assertions below are about the code. */
const CODE = SOURCE.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');

it('is bound to the same-origin proxy, not to backend-api', () => {
  expect(API_BASE_URL).toBe('/api');
});

it('exposes the openapi-fetch verbs the islands call', () => {
  expect(typeof api.GET).toBe('function');
  expect(typeof api.POST).toBe('function');
  expect(typeof api.PUT).toBe('function');
});

it('reads no server-side configuration', () => {
  expect(CODE).not.toContain('astro:env');
  expect(CODE).not.toContain('ORCHESTRATOR_TOKEN');
  expect(CODE).not.toContain('BACKEND_API_URL');
  expect(CODE).not.toContain('api/server');
});

it('takes its types from the generated contract and writes none of its own', () => {
  expect(CODE).toContain("from './schema'");
  expect(CODE).not.toMatch(/\binterface\b/);
});
