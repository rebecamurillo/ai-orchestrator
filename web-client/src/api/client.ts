/**
 * The browser's only fetch caller (AD-1). It is bound to web-client's own origin, so it
 * carries no credential: the proxy at `src/pages/api/[...path].ts` adds the bearer on the
 * server side, and `ORCHESTRATOR_TOKEN` never enters a bundle.
 *
 * The path type is the generated contract with backend-api's `/api/v1` prefix removed,
 * because that prefix is what the proxy adds. Nothing is written by hand here: it is a
 * type-level rename of `paths`, so a route that disappears from the contract disappears
 * from this client too (AD-3). `/healthz` drops out, which is correct — it is backend-api's
 * own health route and is not reachable through the proxy.
 */
import createClient, { type Client } from 'openapi-fetch';

import type { paths } from './schema';

/** Same origin, under the proxy route. Never `BACKEND_API_URL`. */
export const API_BASE_URL = '/api';

export type BrowserPaths = {
  [Path in keyof paths as Path extends `/api/v1${infer Rest}` ? Rest : never]: paths[Path];
};

export const api: Client<BrowserPaths> = createClient<BrowserPaths>({ baseUrl: API_BASE_URL });
