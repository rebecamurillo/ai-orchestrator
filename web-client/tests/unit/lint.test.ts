/**
 * AD-1 is a lint rule, not a convention, and this is what proves it fires.
 *
 * eslint is run over fixture sources given the *path* they would occupy — `lintText` with
 * a virtual `filePath` picks the configuration up from that path without writing anything
 * into `src/`, so a failing run cannot leave a stray module behind for `tsc` or
 * `astro check` to trip over on the next gate.
 */
import { fileURLToPath } from 'node:url';

import { ESLint } from 'eslint';
import { describe, expect, it } from 'vitest';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const RESTRICTED = ['src/islands/Probe.tsx', 'src/stores/probe.ts', 'src/components/probe.ts'];

const eslint = new ESLint({ cwd: ROOT });

async function lint(source: string, filePath: string): Promise<ESLint.LintResult> {
  const [result] = await eslint.lintText(source, { filePath: `${ROOT}${filePath}` });
  return result!;
}

function rules(result: ESLint.LintResult): string[] {
  return result.messages.map((message) => message.ruleId ?? 'fatal');
}

describe.each(RESTRICTED)('%s', (filePath) => {
  it('may not call fetch', async () => {
    const result = await lint('export const load = () => fetch("/api/ping");\n', filePath);

    expect(rules(result)).toContain('no-restricted-globals');
    expect(result.errorCount).toBeGreaterThan(0);
  });

  it('may not import the server-side api module', async () => {
    const result = await lint(
      'import { backend } from "../api/server";\nexport const use = () => backend();\n',
      filePath,
    );

    expect(rules(result)).toContain('no-restricted-imports');
  });

  it('may not import the astro:env server module', async () => {
    const result = await lint(
      'import { ORCHESTRATOR_TOKEN } from "astro:env/server";\nexport const t = ORCHESTRATOR_TOKEN;\n',
      filePath,
    );

    expect(rules(result)).toContain('no-restricted-imports');
  });
});

it('leaves the two api modules free to call fetch', async () => {
  const result = await lint('export const ping = () => fetch("/api/ping");\n', 'src/api/server.ts');

  expect(rules(result)).not.toContain('no-restricted-globals');
});

it('lints the real sources with no error', async () => {
  const results = await eslint.lintFiles(['src', 'tests', 'scripts', 'eslint.config.js']);

  expect(ESLint.getErrorResults(results)).toEqual([]);
});
