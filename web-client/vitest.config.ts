// the reference is what teaches Vite's `UserConfig` about `test`: `getViteConfig` takes a
// Vite config, and the `test` key is Vitest's augmentation of it
/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url';

import { getViteConfig } from 'astro/config';

// `getViteConfig` gives the run Astro's own Vite pipeline, which is what lets a unit test
// import a `.astro` component and render it through `astro/container`. Without it Vitest has
// no transform for `.astro` at all and the component tests cannot exist.
//
// `astro:env/server` is a virtual module Astro materialises during its own build, so even
// with the pipeline a plain Vitest run cannot resolve it. Aliasing it to a double is what
// lets the one module that reads the credential — `src/api/server.ts` — be unit-tested; the
// real module is still type-checked by `astro sync` + `astro check` + `tsc --noEmit` inside
// `pnpm lint`.
export default getViteConfig({
  resolve: {
    alias: {
      'astro:env/server': fileURLToPath(
        new URL('./tests/stubs/astro-env-server.ts', import.meta.url),
      ),
    },
  },
  test: {
    environment: 'node',
    include: ['tests/unit/**/*.test.{ts,tsx}'],
    // Playwright specs are the `e2e-ui` gate and are driven by `pnpm e2e`, never by Vitest
    exclude: ['node_modules/**', 'dist/**', 'tests/e2e/**'],
    // `lint.test.ts` runs eslint over every real source in-process, so its cost grows with the
    // codebase rather than with the suite. It passed at Vitest's 5 s default until Epic 6, then
    // began timing out on CI's slower runner while staying green on a developer machine — a
    // false red that says nothing about the code. The budget is per test, so this buys the one
    // test that needs it without hiding a genuine hang anywhere else.
    testTimeout: 30_000,
    // AD-18: the modules that hold web-client rules are gated at 90 % lines. `src/stores/**`
    // is listed before it exists so the store an island reads from lands under the gate on
    // the day it is written, rather than after someone remembers to widen this list.
    // `.astro` files are left out of the measurement, not out of the suite: v8 maps coverage
    // through the compiled output, where a component's line numbers are not its own.
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json-summary'],
      include: ['src/**/*.{ts,tsx}'],
      thresholds: {
        'src/lib/**': { lines: 90 },
        'src/stores/**': { lines: 90 },
      },
    },
  },
});
