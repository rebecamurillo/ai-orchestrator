/**
 * The backend-api stand-in for `make e2e-ui`.
 *
 * The gate exists to prove what web-client does, and running the real stack would couple
 * it to Postgres and to `make e2e-api`. This answers the two routes the proxy specs need
 * and nothing else; `E2E_BACKEND=real` points the same specs at a real backend-api.
 *
 * `/api/v1/echo-auth` deliberately reflects the credential it was sent. Nothing in this
 * system does that, which is exactly why the proxy must be shown to strip it anyway.
 */
import { createServer } from 'node:http';

const PORT = Number(process.env.STUB_BACKEND_PORT ?? 8788);
const TOKEN = process.env.ORCHESTRATOR_TOKEN ?? '';

const PROBLEM = 'application/problem+json';
const JSON_TYPE = 'application/json';

function send(response, status, type, body, headers = {}) {
  response.writeHead(status, { 'Content-Type': type, ...headers });
  response.end(body);
}

createServer((request, response) => {
  const authorized = request.headers.authorization === `Bearer ${TOKEN}`;
  const { pathname } = new URL(request.url, `http://127.0.0.1:${PORT}`);

  if (!authorized) {
    const body = JSON.stringify({ type: 'about:blank', title: 'unauthorized', status: 401 });
    send(response, 401, PROBLEM, body, { 'WWW-Authenticate': 'Bearer' });
    return;
  }
  if (pathname === '/api/v1/ping') {
    send(response, 200, JSON_TYPE, JSON.stringify({ pong: true }));
    return;
  }
  if (pathname === '/api/v1/echo-auth') {
    send(response, 200, JSON_TYPE, JSON.stringify({ echoed: true }), {
      Authorization: request.headers.authorization,
      'X-Echoed-Credential': request.headers.authorization,
    });
    return;
  }
  send(response, 404, PROBLEM, JSON.stringify({ title: 'not found', status: 404 }));
}).listen(PORT, '127.0.0.1', () => {
  process.stdout.write(`stub backend listening on ${PORT}\n`);
});
