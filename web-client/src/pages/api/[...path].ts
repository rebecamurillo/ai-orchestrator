/**
 * The proxy (AD-1). Every browser call to backend-api goes through here, which is why the
 * browser needs no credential and backend-api needs no CORS headers and no cookies.
 *
 * The route owns the answer to the browser; `src/api/server.ts` owns the request to
 * backend-api. Hop-by-hop headers are dropped in both directions, and every proxied
 * response is uncacheable: these are Run states that change under the Operator, and a
 * cached one would be read as fact.
 *
 * Story 1.5 adds the session guard in `src/middleware.ts`; an unauthenticated call answers
 * 401 rather than redirecting.
 */
import type { APIRoute } from 'astro';

import { NOT_RETURNED, carriesCredential, forward } from '../../api/server';

export const prerender = false;

/** Statuses HTTP defines as having no body; giving one to `Response` is a TypeError. */
const BODILESS = new Set([101, 204, 205, 304]);

export const ALL: APIRoute = async ({ params, request }) => {
  const upstream = await forward(request, params.path ?? '');

  const headers = new Headers();
  upstream.headers.forEach((value, name) => {
    // an upstream that echoed the credential back would otherwise be copied verbatim
    if (NOT_RETURNED.has(name.toLowerCase()) || carriesCredential(value)) return;
    headers.set(name, value);
  });
  headers.set('Cache-Control', 'no-store');

  return new Response(BODILESS.has(upstream.status) ? null : upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers,
  });
};
