/** Story 10.4 (2026-11-26): the editor bar's template type. */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeAll, describe, expect, it } from 'vitest';

import TemplateTypeLine from '../../src/components/templates/TemplateTypeLine.astro';

let container: AstroContainer;

beforeAll(async () => {
  container = await AstroContainer.create();
});

describe('TemplateTypeLine', () => {
  it('prints INTERACTIVE', async () => {
    const html = await container.renderToString(TemplateTypeLine, {
      props: { type: 'interactive' },
    });
    expect(html).toContain('data-testid="templates-type"');
    expect(html).toContain('INTERACTIVE');
  });

  it('prints AUTO', async () => {
    const html = await container.renderToString(TemplateTypeLine, { props: { type: 'auto' } });
    expect(html).toContain('AUTO');
    expect(html).not.toContain('INTERACTIVE');
  });
});
