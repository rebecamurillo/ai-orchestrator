import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';

import MissingWord from '../../src/components/metrics/MissingWord';

it('prints the API word as given', () => {
  expect(renderToStaticMarkup(createElement(MissingWord, { word: 'not recorded' }))).toBe(
    '<span class="metric-missing">not recorded</span>',
  );
});
