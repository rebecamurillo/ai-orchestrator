import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

// `astro:env/server` is a virtual module Astro materialises during its own build, so a
// plain Vitest run cannot resolve it. Aliasing it to a double is what lets the one module
// that reads the credential — `src/api/server.ts` — be unit-tested at all; the real module
// is still type-checked by `astro sync` + `astro check` + `tsc --noEmit` inside `pnpm lint`.
export default defineConfig({
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
