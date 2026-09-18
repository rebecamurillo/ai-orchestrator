/**
 * The visual system is a contract, not a stylesheet convention (UX-DR1).
 *
 * `tokens.css` is the single place a colour, a type role, a spacing step or a layout figure
 * is decided, and every value below is the one `DESIGN.md` fixes. A component that wants a
 * value this file does not carry has to add it here, in front of this test, rather than
 * inventing it locally — which is what keeps twenty screens looking like one instrument.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

export const TOKENS_CSS = readFileSync(
  fileURLToPath(new URL('../../src/styles/tokens.css', import.meta.url)),
  'utf8',
);

/** Every `--name: value` declaration in a stylesheet, in source order. */
export function customProperties(css: string): Map<string, string> {
  const declarations = new Map<string, string>();
  for (const [, name, value] of css.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    declarations.set(name, value.trim().replace(/\s+/g, ' '));
  }
  return declarations;
}

/**
 * `prettier --check` owns the formatting of `tokens.css` inside `make lint`, and it writes
 * a hex in lower case and trims a trailing zero from a decimal — `#0B0D0E` becomes
 * `#0b0d0e`, `0.10em` becomes `0.1em`. Those are the same colour and the same tracking, so
 * both sides are compared through this rather than restating the design's table in
 * prettier's spelling, which would make the table below unreadable against `DESIGN.md`.
 */
function canonical(value: string): string {
  return value.toLowerCase().replace(/(\d*\.\d*?)0+(?=[a-z%]|$)/g, '$1');
}

const TOKENS = customProperties(TOKENS_CSS);

function token(name: string): string | undefined {
  const value = TOKENS.get(name);
  return value === undefined ? undefined : canonical(value);
}

/** UX-DR1's palette plus the diagram-surface fourth signal. Four grounds, two hairlines, three
 *  texts, four signals (criterion added by story 1-5, 2026-09-16 per SPEC.md / AD-15), accent.
 *  Revised: story 1-5 (2026-09-16) — signal-criterion enters tokens for the diagram surface only.
 */
const COLORS: Record<string, string> = {
  '--color-bg': '#0B0D0E',
  '--color-surface': '#111416',
  '--color-surface-raised': '#171B1D',
  '--color-surface-rail': '#0E1113',
  '--color-surface-inset': '#08090A',
  '--color-line': '#21272A',
  '--color-line-strong': '#2C3438',
  '--color-text': '#DDE3E5',
  '--color-text-secondary': '#8B979B',
  '--color-text-tertiary': '#5C686C',
  '--color-signal-run': '#4FB477',
  '--color-signal-needs-you': '#E4B33C',
  '--color-signal-failed': '#E05252',
  '--color-signal-criterion': '#6C8CD5',
  '--color-accent': '#7FD4C1',
};

/**
 * The type ramp: `--type-<role>` is the size, and a role carries `-line`, `-tracking` or
 * `-transform` only where the design states one. Inventing a line-height for a role that
 * has none would make this test assert a value nobody chose.
 */
const TYPE: Record<string, Record<string, string>> = {
  'detail-title': { '': '19px', '-line': '1.3', '-tracking': '-0.01em' },
  question: { '': '14px', '-line': '1.7' },
  command: { '': '13px', '-line': '1.7' },
  body: { '': '13px', '-line': '1.45' },
  'surface-title': { '': '13px', '-tracking': '0.18em', '-transform': 'uppercase' },
  'row-title': { '': '12.5px', '-line': '1.4' },
  'row-body': { '': '12.5px', '-line': '1.55' },
  meta: { '': '11.5px', '-line': '1.45' },
  micro: { '': '11px', '-line': '1.6' },
  'status-token': { '': '11px', '-tracking': '0.10em' },
  control: { '': '11px', '-tracking': '0.12em', '-transform': 'uppercase' },
  eyebrow: { '': '10.5px', '-tracking': '0.16em', '-transform': 'uppercase' },
  'column-head': { '': '10px', '-tracking': '0.18em', '-transform': 'uppercase' },
  'section-head': { '': '10px', '-tracking': '0.22em', '-transform': 'uppercase' },
};

const LAYOUT: Record<string, string> = {
  '--rail-width': '172px',
  '--page-max': '1180px',
  '--detail-max': '940px',
  '--section-gap': '34px',
  // UX-DR5: the record grid is a contract, not a suggestion — type · project · repo · what · age
  '--record-grid': '52px 128px 210px 1fr 74px',
};

describe('colours', () => {
  it.each(Object.entries(COLORS))('%s is %s', (name, value) => {
    expect(token(name)).toBe(canonical(value));
  });

  it('carries no colour beyond the fifteen the design names (fourteen UX-DR1 + signal-criterion, story 1-5 2026-09-16)', () => {
    const declared = [...TOKENS.keys()].filter((name) => name.startsWith('--color-'));

    expect(declared.sort()).toEqual(Object.keys(COLORS).sort());
  });
});

describe('type roles', () => {
  const expected = Object.entries(TYPE).flatMap(([role, parts]) =>
    Object.entries(parts).map(([suffix, value]) => [`--type-${role}${suffix}`, value] as const),
  );

  it.each(expected)('%s is %s', (name, value) => {
    expect(token(name)).toBe(canonical(value));
  });

  it('declares exactly the roles the ramp has, and no more', () => {
    const declared = [...TOKENS.keys()].filter((name) => name.startsWith('--type-'));

    expect(declared.sort()).toEqual(expected.map(([name]) => name).sort());
  });
});

describe('spacing', () => {
  // a 2px base, which is what produces the odd intermediates the design calls out (5 = 10px)
  const steps = Array.from({ length: 16 }, (_, index) => [index + 1, `${(index + 1) * 2}px`]);

  it.each(steps)('--space-%s is %s', (step, value) => {
    expect(token(`--space-${step}`)).toBe(value);
  });

  it('has the odd intermediates the design names', () => {
    expect(token('--space-5')).toBe('10px');
    expect(token('--space-7')).toBe('14px');
    expect(token('--space-9')).toBe('18px');
  });
});

describe('layout', () => {
  it.each(Object.entries(LAYOUT))('%s is %s', (name, value) => {
    expect(token(name)).toBe(canonical(value));
  });
});

describe('typeface', () => {
  it('is one monospace stack', () => {
    const stack = token('--font-mono');

    expect(stack).toBeDefined();
    expect(stack).toContain('monospace');
  });

  it('declares no second family', () => {
    const families = [...TOKENS.keys()].filter((name) => name.startsWith('--font-'));

    expect(families).toEqual(['--font-mono']);
  });
});
