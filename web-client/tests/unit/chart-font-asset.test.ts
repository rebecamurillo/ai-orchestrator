import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const DIR = fileURLToPath(new URL('../../src/assets/fonts/', import.meta.url));

describe('the bundled font subset (story 6 AC4)', () => {
  it('is a woff2 file with its OFL licence beside it', () => {
    expect(existsSync(`${DIR}JetBrainsMono-subset.woff2`)).toBe(true);
    expect(readFileSync(`${DIR}JetBrainsMono-subset.woff2`).subarray(0, 4).toString('latin1')).toBe(
      'wOF2',
    );
    expect(readFileSync(`${DIR}OFL.txt`, 'utf8')).toContain('SIL OPEN FONT LICENSE');
  });

  it('commits neither the release archive nor the full font', () => {
    const names = readdirSync(DIR);
    expect(names.sort()).toEqual(['JetBrainsMono-subset.woff2', 'OFL.txt']);
  });
});
