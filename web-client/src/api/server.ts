/**
 * The server side of AD-1: the only module that knows where backend-api is and what the
 * credential is. Nothing the browser downloads may import it — `eslint.config.js` refuses
 * the import from `src/islands/`, `src/stores/` and `src/components/`, and Astro refuses
 * to bundle `astro:env/server` into client code at all.
 *
 * Two callers: pages and Actions use `backend()`, an openapi-fetch client typed by the
 * generated contract; the proxy route uses `forward()`, which passes a browser request
 * through unchanged apart from the headers listed below.
 */
import createClient, { type Client } from 'openapi-fetch';
import { BACKEND_API_URL, ORCHESTRATOR_TOKEN } from 'astro:env/server';

import type { paths } from './schema';

/** backend-api serves every feature route under this prefix; `/healthz` is outside it. */
export const API_PREFIX = '/api/v1';

/**
 * Headers that describe one hop of a connection, not the message (RFC 9110 §7.6.1).
 * Copying them across a proxy is how a response ends up claiming a framing it does not have.
 */
const HOP_BY_HOP = [
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
];

/**
 * Request headers that belong to the browser's conversation with web-client and mean
 * something different, or nothing, to backend-api. The session cookie is the Operator's
 * (AD-4) and backend-api reads no cookies; `host` would name the wrong server; an
 * `authorization` the browser sent is replaced by the instance credential, never honoured.
 * `accept-encoding` and `content-length` are left to the fetch implementation, which
 * negotiates its own encoding and frames the body it is given.
 */
const NOT_FORWARDED = new Set([
  ...HOP_BY_HOP,
  'cookie',
  'host',
  'authorization',
  'accept-encoding',
  'content-length',
]);

/**
 * Response headers the proxy must not copy. The body is re-framed on the way out and the
 * fetch implementation has already decoded it, so `content-length` and `content-encoding`
 * from upstream would both describe a message the browser is not receiving.
 */
export const NOT_RETURNED = new Set([...HOP_BY_HOP, 'content-length', 'content-encoding']);

function authorization(): string {
  return `Bearer ${ORCHESTRATOR_TOKEN}`;
}

/**
 * Whether a header value carries the instance credential.
 *
 * The proxy is the trust boundary, so it does not assume backend-api never echoes what it
 * was sent: a response header holding the token is dropped rather than copied through.
 * This module is the only one that may ask the question, because it is the only one that
 * knows the answer.
 */
export function carriesCredential(value: string): boolean {
  return ORCHESTRATOR_TOKEN.length > 0 && value.includes(ORCHESTRATOR_TOKEN);
}

/** An openapi-fetch client bound to backend-api, for pages and Actions. */
export function backend(): Client<paths> {
  return createClient<paths>({
    baseUrl: BACKEND_API_URL,
    headers: { Authorization: authorization() },
  });
}

/** The prefix every proxied request resolves inside. */
function versionedBase(): URL {
  return new URL(`${API_PREFIX}/`, BACKEND_API_URL);
}

/**
 * Refused before backend-api is contacted, in the shape the whole API answers errors in.
 * `application/problem+json`, so the browser reads it exactly as it reads a real one.
 */
function invalidPath(path: string): Response {
  return new Response(
    JSON.stringify({
      type: 'about:blank',
      title: 'invalid path',
      status: 400,
      detail: `/api/${path} does not resolve inside ${API_PREFIX}`,
    }),
    { status: 400, headers: { 'Content-Type': 'application/problem+json' } },
  );
}

/**
 * Send one browser request on to backend-api and return its answer untouched.
 *
 * `path` is the part of the URL after `/api/`, so `/api/ping` becomes
 * `${BACKEND_API_URL}/api/v1/ping`. It is resolved against the versioned base rather than
 * concatenated, and refused if it lands outside: `..` segments — percent-encoded ones
 * included, which the router does not decode — would otherwise reach backend-api's
 * unversioned routes carrying the instance credential.
 *
 * The body is read into memory rather than streamed: these are JSON payloads, and a
 * streamed request body needs `duplex: 'half'`, which is not part of `RequestInit`.
 */
export async function forward(request: Request, path: string): Promise<Response> {
  const { search } = new URL(request.url);
  const base = versionedBase();
  const resolved = new URL(`${path}${search}`, base);
  if (!resolved.pathname.startsWith(base.pathname)) return invalidPath(path);
  const target = resolved.toString();

  const headers = new Headers();
  request.headers.forEach((value, name) => {
    if (!NOT_FORWARDED.has(name.toLowerCase())) headers.set(name, value);
  });
  headers.set('Authorization', authorization());

  const hasBody = request.method !== 'GET' && request.method !== 'HEAD';
  return fetch(target, {
    method: request.method,
    headers,
    body: hasBody ? await request.arrayBuffer() : undefined,
    redirect: 'manual',
  });
}
