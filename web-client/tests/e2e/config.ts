/**
 * The values the `e2e-ui` gate runs against, shared by `playwright.config.ts` and the
 * specs so that neither can drift from the other.
 *
 * `PROBE_TOKEN` is a placeholder, not a credential. It is deliberately unmistakable: the
 * credential-leak spec greps the build output, the served HTML and every response header
 * for exactly this string, and a generic value would make those assertions meaningless.
 */
export const PREVIEW_PORT = 4321;
export const PREVIEW_URL = `http://127.0.0.1:${PREVIEW_PORT}`;
export const STUB_BACKEND_PORT = 8788;

export const PROBE_TOKEN = 'e2e-probe-token-must-not-reach-the-browser';
export const PROBE_SESSION_SECRET = 'e2e-probe-session-secret';

/** `E2E_BACKEND=real` runs the same specs against a real backend-api (AD-18). */
export const USE_REAL_BACKEND = process.env.E2E_BACKEND === 'real';

export const BACKEND_API_URL = USE_REAL_BACKEND
  ? (process.env.BACKEND_API_URL ?? 'http://127.0.0.1:8000')
  : `http://127.0.0.1:${STUB_BACKEND_PORT}`;

function realToken(): string {
  const token = process.env.ORCHESTRATOR_TOKEN;
  // an empty bearer would make every spec fail as a 401, which reads as a proxy bug
  if (!token) throw new Error('E2E_BACKEND=real needs ORCHESTRATOR_TOKEN in the environment');
  return token;
}

export const ORCHESTRATOR_TOKEN = USE_REAL_BACKEND ? realToken() : PROBE_TOKEN;
