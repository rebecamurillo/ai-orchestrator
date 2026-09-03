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
    include: ['tests/unit/**/*.test.ts'],
    // Playwright specs are the `e2e-ui` gate and are driven by `pnpm e2e`, never by Vitest
    exclude: ['node_modules/**', 'dist/**', 'tests/e2e/**'],
  },
});
