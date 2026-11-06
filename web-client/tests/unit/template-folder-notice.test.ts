/** `FolderNotice` (story 6, BR-17, AC-13 notice part, 2026-11-06) via `astro/container`. */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeAll, describe, expect, it } from 'vitest';

import FolderNotice from '../../src/components/templates/FolderNotice.astro';

let container: AstroContainer;

beforeAll(async () => {
  container = await AstroContainer.create();
});

function render(props: Record<string, unknown>): Promise<string> {
  return container.renderToString(FolderNotice, { props });
}

function sentence(name: string): string {
  return (
    `A file named ${name}.yaml is in the template folder. At the next reload or start-up, ` +
    `if that file is valid, its content becomes the next version; versions saved here stay ` +
    `listed. A refused file is listed with its errors in the reload answer.`
  );
}

describe('FolderNotice', () => {
  it('renders one needs-you banner holding the exact sentence when inFolder is true', async () => {
    const html = await render({ name: 'agent-smoke', inFolder: true });

    expect(html.match(/<aside/g)).toHaveLength(1);
    expect(html).toContain('data-signal="needs-you"');
    const text = /<aside[^>]*>([\s\S]*?)<\/aside>/.exec(html)?.[1];
    expect(text).toBe(sentence('agent-smoke'));
  });

  it('names the file after the template', async () => {
    const html = await render({ name: 'bench', inFolder: true });

    expect(/<aside[^>]*>([\s\S]*?)<\/aside>/.exec(html)?.[1]).toBe(sentence('bench'));
    expect(html).toContain('bench.yaml');
  });

  it.each([false, undefined, null])('renders nothing when inFolder is %s', async (inFolder) => {
    const html = await render({ name: 'agent-smoke', inFolder });

    expect(html).not.toContain('<aside');
    expect(html).not.toContain('template folder');
  });
});
