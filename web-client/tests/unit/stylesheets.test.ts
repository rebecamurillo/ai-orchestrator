/**
 * The shape rules of UX-DR1, checked over every stylesheet the component tree owns —
 * `src/styles/*.css` plus the scoped `<style>` block of every `.astro` file.
 *
 * Radius, shadow and a stray hex are the three ways an instrument-dark surface turns into a
 * consumer-app surface one component at a time, and none of them shows up in a screenshot
 * review of the screen that introduced it. This file is the gate that does not need a
 * screen to exist yet: a component added in epic 4 is covered the moment it is written.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { TOKENS_CSS, customProperties } from './tokens.test';

const SRC = fileURLToPath(new URL('../../src/', import.meta.url));

// `.astro` sources come through Vite so that a component added anywhere under `src/` is
// covered without being listed here. Vite's own CSS plugin answers `?raw` on a `.css` file
// with an empty string, which would make every rule below pass vacuously, so the `.css`
// files are walked and read from disk instead.
const components = import.meta.glob('../../src/**/*.astro', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

type Sheet = { path: string; css: string };

/** Every `.css` file anywhere under `src/`, not only the ones in `src/styles/`. */
function stylesheetsUnder(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return stylesheetsUnder(path);
    return entry.name.endsWith('.css') ? [path] : [];
  });
}

/** The CSS of one file: a `.css` file whole, an `.astro` file's `<style>` blocks only. */
function sheets(): Sheet[] {
  const stylesheets = stylesheetsUnder(SRC).map((path) => ({
    path: `src/${path.slice(SRC.length)}`,
    css: readFileSync(path, 'utf8'),
  }));

  const scoped = Object.entries(components).flatMap(([path, source]) => {
    const blocks = [...source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(
      (match) => match[1]!,
    );
    return blocks.length > 0
      ? [{ path: path.replace('../../src/', 'src/'), css: blocks.join('\n') }]
      : [];
  });

  return [...stylesheets, ...scoped];
}

const SHEETS = sheets();
const TOKEN_NAMES = new Set(customProperties(TOKENS_CSS).keys());

/** Declarations of one property, as `value` strings, with comments stripped. */
function declarations(css: string, property: string): string[] {
  const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const pattern = new RegExp(`(?<![\\w-])${property}\\s*:\\s*([^;}]+)`, 'g');
  return [...withoutComments.matchAll(pattern)].map((match) => match[1]!.trim());
}

it('finds the stylesheets it is meant to check, and reads them', () => {
  // an empty sheet would make every rule below pass without checking anything
  expect(SHEETS.length).toBeGreaterThan(10);
  expect(SHEETS.map((sheet) => sheet.path)).toContain('src/styles/tokens.css');
  expect(SHEETS.filter((sheet) => sheet.css.trim().length === 0)).toEqual([]);
});

describe.each(SHEETS.map((sheet) => [sheet.path, sheet] as const))('%s', (_path, sheet) => {
  it('rounds no corner', () => {
    const radii = declarations(sheet.css, 'border-radius');

    expect(radii.filter((value) => value !== '0')).toEqual([]);
  });

  it('casts no shadow but the accent inset on the active rail item', () => {
    const shadows = declarations(sheet.css, 'box-shadow');

    expect(
      shadows.filter((value) => value !== 'inset 2px 0 0 var(--color-accent)' && value !== 'none'),
    ).toEqual([]);
  });

  it('sets no font weight above 400', () => {
    const weights = declarations(sheet.css, 'font-weight');

    expect(weights.filter((value) => value !== '400')).toEqual([]);
  });

  it('spells no colour it did not get from a token', () => {
    // `tokens.css` is where a colour is decided; everywhere else reads `var(--color-…)`.
    // A hex is the obvious way round that; `rgb()` and `hsl()` are the quiet ones.
    const literals =
      sheet.path === 'src/styles/tokens.css'
        ? []
        : [...sheet.css.matchAll(/#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|color-mix)\(/g)];

    expect(literals.map((match) => match[0])).toEqual([]);
  });

  it('references only tokens that exist', () => {
    const local = new Set(customProperties(sheet.css).keys());
    const referenced = [...sheet.css.matchAll(/var\(\s*(--[a-z0-9-]+)/g)].map((match) => match[1]!);

    expect(referenced.filter((name) => !TOKEN_NAMES.has(name) && !local.has(name))).toEqual([]);
  });
});

it('never removes an outline', () => {
  // UX-DR19: the focus ring is never removed and never replaced by a background change.
  // `outline: none`, `outline: 0`, `outline: 0px` and `outline-width: 0` all remove it.
  for (const sheet of SHEETS) {
    const removals = [
      ...declarations(sheet.css, 'outline'),
      ...declarations(sheet.css, 'outline-width'),
      ...declarations(sheet.css, 'outline-style'),
    ].filter((value) => /^(none|0)/.test(value));

    expect(removals, sheet.path).toEqual([]);
  }
});

it('styles nothing with a style attribute', () => {
  // `web-client/AGENTS.md`: no inline styles, tokens via CSS variables only. An inline
  // style is invisible to every rule above, so it is the one way round all of them.
  for (const [path, source] of Object.entries(components)) {
    expect([...source.matchAll(/\sstyle="/g)].map(() => path)).toEqual([]);
  }
});

it('declares the focus ring once, in base.css', () => {
  const base = SHEETS.find((sheet) => sheet.path === 'src/styles/base.css');

  expect(base?.css).toContain(':focus-visible');
  expect(declarations(base?.css ?? '', 'outline')).toContain('1px solid var(--color-accent)');
  expect(declarations(base?.css ?? '', 'outline-offset')).toContain('1px');
});

it('uses no media query, because the product declares no breakpoint', () => {
  for (const sheet of SHEETS) {
    expect(sheet.css, sheet.path).not.toContain('@media');
  }
});

it('reads the source of every component under src/', () => {
  // a component that carries no `<style>` at all is fine; a component this glob never saw
  // is not — it would mean the rules above stopped covering the tree
  expect(Object.keys(components).length).toBeGreaterThan(10);
});
