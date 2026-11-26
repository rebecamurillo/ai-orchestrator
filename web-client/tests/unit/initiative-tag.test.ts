import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';

import Tag from '../../src/components/initiatives/Tag';

it('renders a span value without href', () => {
  const html = renderToStaticMarkup(createElement(Tag, { label: 'project', value: 'Familio' }));
  expect(html).toContain('ini-tag-key">project<');
  expect(html).toContain('<span class="ini-tag-value">Familio</span>');
  expect(html).not.toContain('<a');
});

it('renders an anchor value with href', () => {
  const html = renderToStaticMarkup(
    createElement(Tag, { label: 'repo', value: 'api', href: '/x', testId: 't' }),
  );
  expect(html).toContain('<a class="ini-tag-value" href="/x"');
  expect(html).toContain('data-testid="t"');
});
