/**
 * AD-3: no TypeScript type for an API payload is written by hand. `src/api/schema.d.ts`
 * is the only place they exist, it is produced by `pnpm gen:api`, and it says so in its
 * first line so that nobody reaches for it as a place to add one.
 */
import { readFileSync } from 'node:fs';

import { expect, it } from 'vitest';

const SCHEMA = readFileSync(new URL('../../src/api/schema.d.ts', import.meta.url), 'utf8');
const CONTRACT = JSON.parse(
  readFileSync(new URL('../../../contracts/openapi.json', import.meta.url), 'utf8'),
) as { paths: Record<string, unknown> };

it('announces that it is generated', () => {
  expect(SCHEMA.split('\n')[0]).toContain('GENERATED');
  expect(SCHEMA).toContain('pnpm gen:api');
});

it('types every path the exported contract publishes', () => {
  for (const path of Object.keys(CONTRACT.paths)) {
    expect(SCHEMA).toContain(`"${path}"`);
  }
});

it('carries the problem document the whole API answers errors with', () => {
  expect(SCHEMA).toContain('ProblemDetail');
  expect(SCHEMA).toContain('ProblemError');
});
