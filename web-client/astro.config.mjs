// @ts-check
import node from '@astrojs/node';
import react from '@astrojs/react';
import { defineConfig, envField } from 'astro/config';

// AD-1: web-client is the only origin the browser talks to, and it renders on the server,
// so every route is server-rendered and the build target is a standalone Node server.
// AD-20: configuration is the environment. Declaring it here is what makes `astro:env/server`
// a typed module and what keeps these three values out of anything the browser receives —
// `context: 'server', access: 'secret'` is refused at build time if client code imports it.
export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  integrations: [react()],
  // loopback IPv4 only: `astro dev` and `astro preview` are developer-facing servers, and
  // the container serves through the standalone entry with HOST/PORT instead. Naming the
  // address rather than leaving it at `localhost` also keeps the Playwright `webServer`
  // check unambiguous, since `localhost` resolves to both ::1 and 127.0.0.1.
  server: { host: '127.0.0.1', port: 4321 },
  env: {
    schema: {
      // the base URL of backend-api; only `src/api/server.ts` ever reads it
      BACKEND_API_URL: envField.string({ context: 'server', access: 'secret' }),
      // the one credential (AD-4): the bearer the proxy adds, and the login token in 1.5
      ORCHESTRATOR_TOKEN: envField.string({ context: 'server', access: 'secret' }),
      // signs the `orch_session` cookie; declared here, used by 1.5
      ORCHESTRATOR_SESSION_SECRET: envField.string({ context: 'server', access: 'secret' }),
      // which Templates `/workflows/new` offers, comma-separated. `secret` despite carrying
      // no credential: Astro inlines a `public` variable at build time and reads a `secret`
      // one at run time, and the image is built with this unset. The default is `''` because
      // `envField` applies its own only to an absent variable, while blank must mean the
      // default too — `newwf/catalog.ts::parseRootTemplates` owns that fallback.
      ROOT_TEMPLATES: envField.string({
        context: 'server',
        access: 'secret',
        optional: true,
        default: '',
      }),
    },
  },
});
