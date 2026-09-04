/**
 * The two props story 1.5 added to components story 1.4 shipped.
 *
 * `tests/unit/components.test.ts` is the home of the component suite, and it is frozen — it
 * covers those components as 1.4 wrote them, and it still passes unchanged because both
 * additions are optional and default to the previous behaviour. What it cannot cover is
 * behaviour that did not exist when it was written, so that lives here.
 *
 * Both props are load-bearing rather than decorative: without `type` the login form has no
 * control that submits it, and without `action` the Board readout never names the surface
 * that changes what it says.
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeAll, describe, expect, it } from 'vitest';

import Button from '../../src/components/Button.astro';
import EmptyState from '../../src/components/EmptyState.astro';

let container: AstroContainer;

beforeAll(async () => {
  container = await AstroContainer.create();
});

function render(
  component: Parameters<AstroContainer['renderToString']>[0],
  props: Record<string, unknown>,
): Promise<string> {
  return container.renderToString(component, { props });
}

describe('Button.type', () => {
  it('submits the form it closes when it is asked to', async () => {
    // a `type="button"` control inside a form does nothing at all when clicked, which would
    // present as a login screen whose Enter key works and whose button does not
    const html = await render(Button, { label: 'ENTER', type: 'submit' });

    expect(html).toMatch(/<button[^>]*type="submit"/);
  });

  it('is still a plain button when nothing asks otherwise', async () => {
    const html = await render(Button, { label: 'VALIDATE' });

    expect(html).toMatch(/<button[^>]*type="button"/);
  });

  it('is not rendered on the link form, which has no type to give', async () => {
    const html = await render(Button, {
      label: 'START RUN',
      href: '/workflows/new',
      type: 'submit',
    });

    expect(html).toMatch(/<a[^>]*href="\/workflows\/new"/);
    expect(html).not.toContain('type="submit"');
  });
});

describe('EmptyState.action', () => {
  const readout = {
    testId: 'board-empty',
    headline: 'NOTHING REGISTERED',
    lines: ['No project is registered, so no run can be started.'],
  };

  it('names the surface that changes the readout, as a link', async () => {
    const html = await render(EmptyState, {
      ...readout,
      action: { label: 'register a project to start', href: '/projects' },
    });

    expect(html).toMatch(/<a[^>]*href="\/projects"[^>]*>register a project to start<\/a>/);
  });

  it('keeps the action after the lines, never instead of them', async () => {
    const html = await render(EmptyState, {
      ...readout,
      action: { label: 'register a project to start', href: '/projects' },
    });

    expect(html).toContain('No project is registered, so no run can be started.');
    expect(html.indexOf('No project is registered')).toBeLessThan(html.indexOf('/projects'));
  });

  it('renders no link at all when the readout names no surface', async () => {
    const html = await render(EmptyState, readout);

    expect(html).not.toContain('<a');
  });
});
