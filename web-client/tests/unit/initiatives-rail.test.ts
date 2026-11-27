/** Story 10.1: the Initiatives rail item (EXPERIENCE § 2b, 2026-11-22). */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeAll, describe, expect, it } from 'vitest';

import AppRail from '../../src/components/AppRail.astro';
import Shell from '../../src/layouts/Shell.astro';

let container: AstroContainer;
beforeAll(async () => {
  container = await AstroContainer.create();
});

const rail = (props: Record<string, unknown>) => container.renderToString(AppRail, { props });
const item = (html: string, id: string) =>
  html.match(new RegExp(`<a[^>]*nav-${id}"[\\s\\S]*?</a>`))![0];

describe('AppRail Initiatives item', () => {
  it('AC1: first item, with count and need-you line', async () => {
    const html = await rail({ active: 'workflows', initiatives: 6, initiativesNeedYou: 2 });
    expect(html.indexOf('nav-initiatives"')).toBeLessThan(html.indexOf('nav-workflows'));
    expect(html.indexOf('nav-initiatives"')).toBeGreaterThan(-1);
    const a = item(html, 'initiatives');
    expect(a).toContain('href="/initiatives"');
    expect(a).toContain('class="count');
    expect(a).toContain('>6<');
    expect(html).toMatch(
      /data-testid="nav-initiatives-needs-you"[^>]*data-signal="needs-you"[^>]*>\s*2 need you|data-signal="needs-you"[^>]*data-testid="nav-initiatives-needs-you"[^>]*>\s*2 need you/,
    );
  });

  it('AC2: absent at zero', async () => {
    const html = await rail({ active: 'workflows', initiatives: 0, initiativesNeedYou: 0 });
    expect(html).not.toContain('nav-initiatives-needs-you');
    expect(item(html, 'initiatives')).not.toContain('count');
  });

  it('AC2: only the active item is current', async () => {
    const html = await rail({ active: 'initiatives' });
    expect(html.match(/aria-current="page"/g)).toHaveLength(1);
    expect(item(html, 'initiatives')).toContain('aria-current="page"');
  });

  it('AC2: Shell forwards both props', async () => {
    const html = await container.renderToString(Shell, {
      props: { active: 'initiatives', title: 'INITIATIVES', initiatives: 4, initiativesNeedYou: 1 },
    });
    expect(item(html, 'initiatives')).toContain('>4<');
    expect(html).toContain('1 need you');
  });

  it('leaves the Workflows need-you line unchanged', async () => {
    const html = await rail({ active: 'workflows', needsYou: 3 });
    expect(html).toContain('nav-needs-you');
    expect(html).toContain('3 need you');
    expect(html).not.toContain('nav-initiatives-needs-you');
  });
});
