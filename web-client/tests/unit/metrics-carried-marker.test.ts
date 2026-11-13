import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';

import CarriedMarker from '../../src/components/metrics/CarriedMarker';

it('reads from v{n}', () => {
  expect(renderToStaticMarkup(createElement(CarriedMarker, { from: 2 }))).toContain('from v2');
});
