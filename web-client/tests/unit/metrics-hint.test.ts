import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';

import Hint from '../../src/components/metrics/Hint';
import { entry } from './metrics-fixtures';

const html = (props: Parameters<typeof Hint>[0]) =>
  renderToStaticMarkup(createElement(Hint, props));

it('shows the rows from the entry of the method the value used', () => {
  const e = entry('cost.total', { limits: 'a limit' });
  const out = html({ entry: e, methodId: 'cost.total@1' });
  expect(out).toContain('role="dialog"');
  expect(out).not.toContain('aria-modal');
  expect(out).toContain('cost.total · cost.total@1');
  for (const term of ['WHAT', 'HOW', 'SOURCE', 'LIMITS', 'MISSING']) expect(out).toContain(term);
  expect(out).toContain('how cost.total v1');
  expect(out).not.toContain('how cost.total v2');
  expect(out).toContain('source of cost.total');
  expect(out).toContain('a limit');
  expect(out).toContain('not recorded · not available');
});

it('omits LIMITS when the entry has none and defaults to the latest method', () => {
  const out = html({ entry: entry() });
  expect(out).not.toContain('LIMITS');
  expect(out).toContain('cost.total@2');
  expect(out).toContain('how cost.total v2');
});

it('lists each flagged method with the Runs that used it', () => {
  const out = html({
    entry: entry(),
    flagged: [
      { methodId: 'cost.total@1', runs: ['Run 1', 'Run 2'] },
      { methodId: 'cost.total@2', runs: ['Run 3'] },
    ],
  });
  expect(out).toContain('how cost.total v1');
  expect(out).toContain('how cost.total v2');
  expect(out).toContain('Runs: Run 1, Run 2');
  expect(out).toContain('Runs: Run 3');
});
