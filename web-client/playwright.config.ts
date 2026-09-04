import { defineConfig } from '@playwright/test';

import {
  BACKEND_API_URL,
  ORCHESTRATOR_TOKEN,
  PREVIEW_URL,
  PROBE_SESSION_SECRET,
  STUB_BACKEND_PORT,
  USE_REAL_BACKEND,
} from './tests/e2e/config';
import { authenticatedStorageState } from './tests/e2e/session';

/**
 * The `e2e-ui` gate. `make e2e-ui` is `pnpm build && pnpm e2e`, so `dist/` is on disk
 * before the preview server starts and the credential spec has a build to grep.
 *
 * The preview server is given the environment `astro:env/server` declares. Those values
 * are placeholders (`tests/e2e/config.ts`), which is what makes "the token appears in no
 * response header, HTML, or client bundle" a checkable claim rather than a hope.
 *
 * Since 1.5 every route is behind the session guard, so the run carries a valid
 * `orch_session` by default (`tests/e2e/session.ts`) — the state the product is in whenever
 * anyone is looking at it. A spec whose subject is the guard itself opts out with
 * `test.use({ storageState: NO_SESSION })`.
 */
const stubBackend = {
  command: 'node tests/e2e/stub-backend.mjs',
  url: `http://127.0.0.1:${STUB_BACKEND_PORT}/api/v1/ping`,
  reuseExistingServer: false,
  env: { STUB_BACKEND_PORT: String(STUB_BACKEND_PORT), ORCHESTRATOR_TOKEN },
};

const preview = {
  // `pnpm preview` runs the standalone entry directly rather than `astro preview`, which
  // in Astro 7 daemonises and returns — Playwright reads that as a server that exited.
  // It is also exactly the process the container runs in 1.6.
  command: 'pnpm preview',
  // `url`, not `port`: Playwright's port check covers every address the host resolves to,
  // and the preview server binds 127.0.0.1 only
  url: PREVIEW_URL,
  reuseExistingServer: false,
  env: {
    BACKEND_API_URL,
    ORCHESTRATOR_TOKEN,
    ORCHESTRATOR_SESSION_SECRET: PROBE_SESSION_SECRET,
  },
};

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  reporter: [['list']],
  use: { baseURL: PREVIEW_URL, storageState: authenticatedStorageState() },
  webServer: USE_REAL_BACKEND ? [preview] : [stubBackend, preview],
});
