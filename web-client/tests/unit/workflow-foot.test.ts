import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';

import WorkflowFoot from '../../src/components/initiatives/WorkflowFoot';

it('joins the workflows and marks the current one', () => {
  const html = renderToStaticMarkup(
    createElement(WorkflowFoot, {
      current: 'build',
      workflows: [
        { workflow: 'spec', type: 'interactive', state: 'completed' },
        { workflow: 'build', type: 'auto', state: 'ongoing' },
        { workflow: 'deploy', type: 'auto', state: null },
      ],
    }),
  );
  const text = html.replace(/<[^>]*>/g, '');
  expect(text).toBe('spec · completed ▸ build · ongoing ▸ deploy');
  expect(html.match(/data-current="true"/g)).toHaveLength(1);
  expect(html).toMatch(/data-current="true"[^>]*>[^]*build · ongoing/);
});
