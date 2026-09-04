/**
 * Prove that every module under `src/` has a test module that names it (AD-18).
 *
 * `pnpm lint` runs this, so the rule fails the same gate as eslint and prettier rather than
 * living in prose. The backend half is `scripts/check_test_pairs.py`; the two answer the
 * same question about the two components.
 *
 * A module counts as paired when some file under `tests/unit/` names it — as an import
 * specifier resolved against the test file, or as a package-relative path. The second form
 * is not a loophole: `tests/unit/lint.test.ts` names `src/api/server.ts` as the virtual file
 * it lints, which is the only way to exercise a module the browser must never load. Only
 * strings that resolve to a real file under `src/` count, and imports between two source
 * modules are never followed — otherwise everything a page pulls in would look tested.
 *
 * Exempt: `*.d.ts` (ambient and generated declarations, including `src/api/schema.d.ts`,
 * whose gate is the drift check in `make lint`) and `src/pages/**\/*.astro` (route templates,
 * whose gate is `make e2e-ui`).
 *
 * Usage: `node scripts/check-test-pairs.mjs [--src PATH] [--tests PATH]`. The flags default
 * to this package and exist so `tests/unit/check-test-pairs.test.ts` can drive the gate
 * against scratch trees and prove it fires.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const argv = process.argv.slice(2);

function flag(name, fallback) {
  const at = argv.indexOf(name);
  if (at === -1) return fallback;
  const value = argv[at + 1];
  if (value === undefined) {
    process.stderr.write(`${name}: expects a path\n`);
    process.exit(1);
  }
  return resolve(value);
}

const SRC = flag('--src', join(PACKAGE_ROOT, 'src'));
const TESTS = flag('--tests', join(PACKAGE_ROOT, 'tests', 'unit'));
/** What a non-relative reference such as `src/api/server.ts` is resolved against. */
const ROOT = dirname(SRC);

const SOURCE_EXTENSIONS = ['.ts', '.tsx', '.astro'];
/** Tried in order after a specifier that carries no extension of its own. */
const CANDIDATE_SUFFIXES = ['', '.ts', '.tsx', '.astro', '/index.ts', '/index.tsx'];
const QUOTED = /'([^'\n]+)'|"([^"\n]+)"|`([^`\n$]+)`/g;

function walk(directory) {
  const found = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) found.push(...walk(path));
    else found.push(path);
  }
  return found.sort();
}

function isExempt(path) {
  if (path.endsWith('.d.ts')) return true;
  return path.endsWith('.astro') && path.startsWith(join(SRC, 'pages') + sep);
}

function sourceModules() {
  return walk(SRC).filter(
    (path) => SOURCE_EXTENSIONS.some((extension) => path.endsWith(extension)) && !isExempt(path),
  );
}

/** Every quoted string in a file — import specifiers and the paths a test names outright. */
function references(file) {
  const found = new Set();
  for (const match of readFileSync(file, 'utf8').matchAll(QUOTED)) {
    const value = match[1] ?? match[2] ?? match[3];
    if (value) found.add(value);
  }
  return found;
}

function resolveCandidates(reference, from) {
  const base = reference.startsWith('.')
    ? resolve(dirname(from), reference)
    : join(ROOT, reference);
  return CANDIDATE_SUFFIXES.map((suffix) => base + suffix);
}

function namedModules() {
  const named = new Set();
  for (const test of walk(TESTS)) {
    for (const reference of references(test)) {
      for (const candidate of resolveCandidates(reference, test)) {
        if (candidate.startsWith(SRC + sep)) named.add(candidate);
      }
    }
  }
  return named;
}

for (const [flagName, directory] of [
  ['--src', SRC],
  ['--tests', TESTS],
]) {
  try {
    if (!statSync(directory).isDirectory()) throw new Error('not a directory');
  } catch {
    process.stderr.write(`${directory}: ${flagName} is not a directory\n`);
    process.exit(1);
  }
}

const named = namedModules();
const orphans = sourceModules().filter((path) => !named.has(path));

if (orphans.length > 0) {
  for (const path of orphans) {
    process.stderr.write(
      `${relative(ROOT, path)}: no module under ${relative(ROOT, TESTS)} names it — ` +
        'every source module has a test module (AD-18)\n',
    );
  }
  process.stderr.write(`test pairs: ${orphans.length} source module(s) without a test module\n`);
  process.exit(1);
}

const checked = sourceModules().length;
process.stdout.write(
  `test pairs: ${checked} module${checked === 1 ? '' : 's'} under ${relative(ROOT, SRC)}, ` +
    `each named by a module under ${relative(ROOT, TESTS)}\n`,
);
