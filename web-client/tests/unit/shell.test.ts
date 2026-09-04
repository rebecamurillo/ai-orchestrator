/**
 * The layout every guarded route renders inside (UX-DR3).
 *
 * `components.test.ts` renders the three shell parts on their own; what only shows up when
 * they are assembled is the composition — that the page slot lands inside `main`, that the
 * document carries a language and a title, and that the counts the caller passes reach the
 * rail and the footer rather than one of them. A shell that dropped its slot would leave
 * every screen blank with every component test still green.
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeAll, expect, it } from 'vitest';

import Shell from '../../src/layouts/Shell.astro';

let container: AstroContainer;

beforeAll(async () => {
  container = await AstroContainer.create();
});

function render(props: Record<string, unknown> = {}, slot = '<p data-testid="page">BODY</p>') {
  return container.renderToString(Shell, {
    props: { active: 'runs', title: 'RUNS', ...props },
    slots: { default: slot },
  });
}

it('renders a document with the surface title in its <title>', async () => {
  const html = await render();

  expect(html).toContain('<html lang="en"');
  expect(html).toContain('RUNS · ai-orchestrator');
});

it('puts the three shell parts around the page slot', async () => {
  const html = await render();

  expect(html).toContain('data-testid="nav-runs"');
  expect(html).toContain('data-testid="surface-title"');
  expect(html).toContain('data-testid="footer-readout"');
  expect(html).toMatch(/<main[^>]*>\s*<p data-testid="page">BODY<\/p>\s*<\/main>/);
});

it('passes the needs-you count to the rail and the footer, not to one of them', async () => {
  const html = await render({ needsYou: 3, running: 2, queued: 1 });
  const footer = html.slice(html.indexOf('data-testid="footer-readout"'));

  expect(html).toContain('data-testid="nav-needs-you"');
  expect(footer).toContain('3');
  expect(footer).toContain('2');
  expect(footer).toContain('1');
});

it('defaults every figure to zero and the timestamp to an em dash', async () => {
  const html = await render();
  const footer = html.slice(html.indexOf('data-testid="footer-readout"'));

  expect(footer).toContain('—');
  expect(html).not.toContain('data-testid="nav-needs-you"');
});
