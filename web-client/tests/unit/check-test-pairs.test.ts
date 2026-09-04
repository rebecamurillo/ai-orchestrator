/**
 * The web-client half of the AD-18 rule "every `src` module has a test module".
 *
 * `pnpm lint` runs the script, so a module added under `src/` with nothing under
 * `tests/unit/` naming it fails the gate rather than shipping untested. The scratch trees
 * below are what prove the gate fires; the last case runs it against this package, which is
 * what `make lint` does.
 */
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { beforeEach, expect, it } from 'vitest';

const SCRIPT = fileURLToPath(new URL('../../scripts/check-test-pairs.mjs', import.meta.url));
const PACKAGE_ROOT = fileURLToPath(new URL('../../', import.meta.url));

let root: string;

function write(relative: string, contents = ''): void {
  const path = join(root, relative);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, contents);
}

function check(src = join(root, 'src'), tests = join(root, 'tests', 'unit')) {
  const run = spawnSync(process.execPath, [SCRIPT, '--src', src, '--tests', tests], {
    encoding: 'utf8',
  });
  return { status: run.status, stdout: run.stdout, stderr: run.stderr };
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'test-pairs-'));
  write('src/lib/session.ts', 'export const value = 1;\n');
  write('tests/unit/session.test.ts', "import { value } from '../../src/lib/session';\n");
});

it('accepts a tree where every module is imported by a test', () => {
  const run = check();

  expect(run.status).toBe(0);
  expect(run.stdout).toContain('1 module');
});

it('refuses a module no test names, and names it', () => {
  write('src/lib/orphan.ts', 'export const other = 2;\n');

  const run = check();

  expect(run.status).not.toBe(0);
  expect(run.stderr).toContain('src/lib/orphan.ts');
});

it('accepts an extensionless import specifier and a directory index', () => {
  write('src/lib/widget/index.ts', 'export const widget = 3;\n');
  write('tests/unit/widget.test.ts', "await import('../../src/lib/widget');\n");

  expect(check().status).toBe(0);
});

it('accepts a module named by a package-relative path rather than imported', () => {
  // `tests/unit/lint.test.ts` names `src/api/server.ts` as a virtual file path: the module
  // cannot be imported into the eslint run, and it is still that test's subject.
  write('src/api/server.ts', 'export const backend = 4;\n');
  write('tests/unit/lint.test.ts', "const file = 'src/api/server.ts';\nexport { file };\n");

  expect(check().status).toBe(0);
});

it('exempts generated and ambient declarations, and page routes', () => {
  write('src/api/schema.d.ts', 'export type Nope = never;\n');
  write('src/env.d.ts', '');
  write('src/pages/index.astro', '<p>page</p>\n');

  expect(check().status).toBe(0);
});

it('does not exempt a component or a layout for being an .astro file', () => {
  write('src/layouts/Shell.astro', '<slot />\n');

  const run = check();

  expect(run.status).not.toBe(0);
  expect(run.stderr).toContain('src/layouts/Shell.astro');
});

it('does not count a module imported only by another source module', () => {
  write('src/lib/session.ts', "import { hidden } from './hidden';\nexport const value = hidden;\n");
  write('src/lib/hidden.ts', 'export const hidden = 5;\n');

  const run = check();

  expect(run.status).not.toBe(0);
  expect(run.stderr).toContain('src/lib/hidden.ts');
});

it('reports a missing tree rather than passing', () => {
  const run = check(join(root, 'nowhere'));

  expect(run.status).not.toBe(0);
  expect(run.stderr).toContain('nowhere');
});

it('is part of the lint gate rather than a script nothing calls', () => {
  const scripts = JSON.parse(readFileSync(join(PACKAGE_ROOT, 'package.json'), 'utf8')).scripts;

  expect(scripts.lint).toContain('scripts/check-test-pairs.mjs');
});

it('passes over this package, the way `pnpm lint` runs it', () => {
  const run = check(join(PACKAGE_ROOT, 'src'), join(PACKAGE_ROOT, 'tests', 'unit'));

  expect(run.stderr).toBe('');
  expect(run.status).toBe(0);
});
