/**
 * UX-DR19 computed rather than claimed.
 *
 * A dark palette is where contrast quietly fails: four near-black grounds that differ by a
 * few units each, three greys stacked on top of them. The ratios are derived from the same
 * `tokens.css` the components read, so nudging a ground one step lighter to "make a panel
 * read" cannot pass this file without also passing WCAG.
 */
import { describe, expect, it } from 'vitest';

import { TOKENS_CSS, customProperties } from './tokens.test';

const TOKENS = customProperties(TOKENS_CSS);

const AA_TEXT = 4.5;
// WCAG 2.2 1.4.3 large-text / 1.4.11 non-text threshold: tertiary carries meta, never prose
const AA_INCIDENTAL = 3;

function channel(component: number): number {
  const unit = component / 255;
  return unit <= 0.04045 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
}

/** WCAG 2.2 relative luminance of a `#rrggbb` token. */
function luminance(hex: string): number {
  const [red, green, blue] = [1, 3, 5].map((offset) =>
    channel(Number.parseInt(hex.slice(offset, offset + 2), 16)),
  );
  return 0.2126 * red! + 0.7152 * green! + 0.0722 * blue!;
}

function token(name: string): string {
  const value = TOKENS.get(name);
  if (!value) throw new Error(`${name} is not declared in tokens.css`);
  return value;
}

export function contrast(foreground: string, background: string): number {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter! + 0.05) / (darker! + 0.05);
}

const GROUNDS = ['--color-bg', '--color-surface', '--color-surface-raised', '--color-surface-rail'];

describe.each(['--color-text', '--color-text-secondary'])('%s', (text) => {
  it.each(GROUNDS)(`reaches AA on %s`, (ground) => {
    const ratio = contrast(token(text), token(ground));

    expect(ratio, `${text} on ${ground} is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(AA_TEXT);
  });
});

describe('--color-text-tertiary', () => {
  it.each(['--color-bg', '--color-surface'])('reaches 3:1 on %s', (ground) => {
    const ratio = contrast(token('--color-text-tertiary'), token(ground));

    expect(
      ratio,
      `--color-text-tertiary on ${ground} is ${ratio.toFixed(2)}:1`,
    ).toBeGreaterThanOrEqual(AA_INCIDENTAL);
  });

  it('is the dimmest text the palette has', () => {
    const tertiary = luminance(token('--color-text-tertiary'));

    expect(tertiary).toBeLessThan(luminance(token('--color-text-secondary')));
    expect(luminance(token('--color-text-secondary'))).toBeLessThan(
      luminance(token('--color-text')),
    );
  });
});

describe('the ground planes', () => {
  // "A raised element is lighter, and never by more than one step" — the tonal order is the
  // only depth device in the system, so an inverted pair would read as a rendering fault.
  it('rise in the fixed order inset < bg < rail < surface < raised', () => {
    const order = [
      '--color-surface-inset',
      '--color-bg',
      '--color-surface-rail',
      '--color-surface',
      '--color-surface-raised',
    ].map((name) => luminance(token(name)));

    expect(order).toEqual([...order].sort((a, b) => a - b));
  });
});

describe('the signal colours', () => {
  // colour reinforces a word token; it never has to be read on its own, but it must be
  // legible where it is drawn — the chip and its three letters sit on a ground or a panel
  it.each(['--color-signal-run', '--color-signal-needs-you', '--color-signal-failed'])(
    '%s reaches 3:1 on bg and surface',
    (signal) => {
      for (const ground of ['--color-bg', '--color-surface']) {
        const ratio = contrast(token(signal), token(ground));

        expect(ratio, `${signal} on ${ground} is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
          AA_INCIDENTAL,
        );
      }
    },
  );
});
