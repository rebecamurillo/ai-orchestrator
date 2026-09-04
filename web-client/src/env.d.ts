/**
 * What `src/middleware.ts` puts on `Astro.locals` for the rest of the request.
 *
 * `authenticated` is written by the middleware and read by pages; it is a fact about the
 * request that has already been decided, never a second place the decision is made. The
 * middleware is the only writer.
 */
declare namespace App {
  interface Locals {
    /** Whether this request arrived with a valid `orch_session` cookie (AD-4). */
    authenticated: boolean;
  }
}
