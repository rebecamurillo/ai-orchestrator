/**
 * The unit-test double for Astro's `astro:env/server` virtual module.
 *
 * Every value here is a visible placeholder, never a credential: the token exists so a
 * test can assert that `Authorization: Bearer <it>` was sent and that no response carries
 * it back. `vitest.config.ts` aliases the virtual module to this file.
 */
export const BACKEND_API_URL = 'http://backend-api.invalid:8000';
export const ORCHESTRATOR_TOKEN = 'unit-placeholder-token';
export const ORCHESTRATOR_SESSION_SECRET = 'unit-placeholder-session-secret';
/** Blank: what an instance that sets nothing has, meaning "offer the default list". */
export const ROOT_TEMPLATES = '';
