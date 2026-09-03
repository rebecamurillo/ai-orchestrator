/**
 * The drift gate itself, run as `make lint` runs it.
 *
 * AD-3 turns on this one command: without it a hand edit to `src/api/schema.d.ts`, or a
 * backend schema change nobody regenerated, reaches the browser as a type that lies. The
 * Makefile test proves the recipe carries `--check`; this proves `--check` refuses.
 */
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, it } from 'vitest';

const SCRIPT = fileURLToPath(new URL('../../scripts/gen-api.mjs', import.meta.url));
const COMMITTED = fileURLToPath(new URL('../../src/api/schema.d.ts', import.meta.url));
const DRIFTED = '// GENERATED but edited by hand\nexport type Nope = never;\n';

function gen(...args: string[]): { status: number | null; stderr: string } {
  const run = spawnSync(process.execPath, [SCRIPT, ...args], { encoding: 'utf8' });
  return { status: run.status, stderr: run.stderr };
}

function scratch(contents: string): string {
  const path = join(mkdtempSync(join(tmpdir(), 'gen-api-')), 'schema.d.ts');
  writeFileSync(path, contents);
  return path;
}

it('accepts a file that matches the contract', () => {
  const target = scratch(readFileSync(COMMITTED, 'utf8'));

  const run = gen('--check', '--output', target);

  expect(run.status).toBe(0);
});

it('refuses a hand-edited file and names it', () => {
  const target = scratch(DRIFTED);

  const run = gen('--check', '--output', target);

  expect(run.status).not.toBe(0);
  expect(run.stderr).toContain('schema.d.ts');
  expect(run.stderr).toContain('out of date');
});

it('does not repair the file it is checking', () => {
  const target = scratch(DRIFTED);

  gen('--check', '--output', target);

  expect(readFileSync(target, 'utf8')).toBe(DRIFTED);
});

it('regenerates the file when not checking', () => {
  const target = scratch(DRIFTED);

  const run = gen('--output', target);

  expect(run.status).toBe(0);
  expect(readFileSync(target, 'utf8')).toBe(readFileSync(COMMITTED, 'utf8'));
});
