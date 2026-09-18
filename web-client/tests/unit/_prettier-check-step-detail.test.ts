/**
 * Enforces Prettier formatting on `StepDetail.tsx` (story 1-2, AD-15).
 *
 * `make lint` already runs `prettier --check .` across the whole tree; this
 * test provides a targeted failure message that names the file and shows the
 * diff, making formatting regressions in the island easier to diagnose.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';

import prettier from 'prettier';
import { it, expect } from 'vitest';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '../../');
const filePath = join(ROOT, 'src/islands/StepDetail.tsx');

it('StepDetail.tsx is formatted by prettier', async () => {
  const source = readFileSync(filePath, 'utf8');
  const config = await prettier.resolveConfig(filePath);
  const formatted = await prettier.format(source, { ...config, filepath: filePath });
  expect(source).toBe(formatted);
});
